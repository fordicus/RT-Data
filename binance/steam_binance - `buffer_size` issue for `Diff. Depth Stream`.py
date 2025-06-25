"""
How to Use:
    Import this module and run with:
        uvicorn steam_binance:app --host 0.0.0.0 --port 8000
        uvicorn steam_binance:app --host 0.0.0.0 --port 8000 --log-level debug
    Monitor:
        http://localhost:8000/health/live
        http://localhost:8000/state/BTCUSDC
        http://localhost:8000/state/BTCUSDC/recent-diffs
        http://localhost:8000/debug/BTCUSDC/events
Dependencies:
    - Python 3.10+
    - aiohttp
    - websockets
    - orjson
    - sortedcontainers
    - pydantic
    - FastAPI
    - prometheus_client
    - uvicorn
    - psutil
    - gc
Functionality:
    Real-time Level 2 order book for Binance Spot:
    • diff streams + REST snapshot alignment + gap recovery
    • combined WS stream for all symbols
    • float-based book for performance
    • robust metrics, logs, debug APIs, dynamic config
IO:
    • Prometheus metrics on :8001
    • HTTP API on :8000 (health, state, snapshots, debug, admin)
"""

import os
import asyncio
import logging
import time
import queue
import gc
from collections import deque
from typing import Any, Dict, List

import aiohttp
import websockets
import orjson
import psutil
from sortedcontainers import SortedDict
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import (
    Counter, Histogram, Gauge, start_http_server, REGISTRY
)
from logging.handlers import QueueHandler, QueueListener
import uvicorn
from dotenv import load_dotenv

# —————— 디버그 플래그 ——————
DEBUG = os.getenv("ORDERBOOK_DEBUG", "false").lower() in ("1", "true", "yes")
# ———————————————————————

# Load environment settings
load_dotenv()

from pydantic import model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_KEY: str
    REST_ENDPOINT: str = "https://api.binance.com/api/v3/depth"
    WS_ENDPOINT: str = "wss://stream.binance.com:9443/stream"
    SYMBOLS: List[str] = ["BTCUSDC"]
    LIMIT: int = 100
    INIT_TIMEOUT: int = 30
    QUEUE_MAXSIZE: int = 10000

    @model_validator(mode="before")
    @classmethod
    def check_api_key(cls, values: dict) -> dict:
        if not values.get("API_KEY"):
            raise ValueError("API_KEY must be set in environment")
        return values

settings = Settings()

# ---------------------------
# Structured JSON Logging
# ---------------------------
class OrjsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record),
            "service": "orderbook",
            "level": record.levelname,
            "symbol": getattr(record, "symbol", None),
            "message": record.getMessage()
        }
        return orjson.dumps(payload).decode()

log_queue: queue.Queue = queue.Queue()
queue_handler = QueueHandler(log_queue)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(OrjsonFormatter())
listener = QueueListener(log_queue, stream_handler, respect_handler_level=True)

logger = logging.getLogger("orderbook")
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
logger.addHandler(queue_handler)
listener.start()

# ---------------------------
# Prometheus Metrics
# ---------------------------
snapshot_latency      = Histogram("snapshot_latency_seconds",   "REST snapshot latency")
snapshot_retries      = Counter("snapshot_retry_total",        "REST snapshot retries",       ["symbol"])
snapshot_last_status  = Gauge("snapshot_last_status",          "Last snapshot HTTP status",   ["symbol"])

diffs_received        = Counter("orderbook_diffs_received_total", "Count of diffs received", ["symbol"])
recoveries_total      = Counter("orderbook_recoveries_total",     "Count of gap recoveries",    ["symbol"])
recovery_success      = Counter("orderbook_recovery_success_total", "Count of successful recoveries", ["symbol"])
recovery_fail         = Counter("orderbook_recovery_fail_total",   "Count of failed recoveries", ["symbol"])

buffer_size           = Gauge("buffer_size",                   "Current buffer size",         ["symbol"])
queue_latency         = Histogram("orderbook_queue_latency_seconds", "Time diff enqueued→dequeued", ["symbol"])
queue_overflows       = Counter("orderbook_queue_overflows_total",   "Total queue overflows",  ["symbol"])

book_last_update      = Gauge("last_update_id",               "Last update ID",              ["symbol"])
gap_size_hist         = Histogram("orderbook_gap_size",        "Distribution of gap sizes",   ["symbol"])
process_latency       = Histogram("orderbook_diff_process_seconds", "Latency from receive to apply_diff", ["symbol"])

ws_connected          = Gauge("ws_connected",                 "WebSocket connection state (1=up,0=down)", ["symbol"])
ws_reconnect_count    = Gauge("ws_reconnect_count",           "Number of WS reconnects",     ["symbol"])

process_cpu           = Gauge("process_cpu_percent",          "CPU percent of process",      ["symbol"])
process_mem           = Gauge("process_memory_rss_bytes",     "Memory RSS bytes of process", ["symbol"])
uptime                = Gauge("process_uptime_seconds",       "Time since last connect",     ["symbol"])

gc_pause_hist         = Histogram("python_gc_pause_seconds",   "GC pause duration")

# ---------------------------
# Global State
# ---------------------------
orderbook: Dict[str, Dict[str, Any]] = {}
buffers:   Dict[str, asyncio.Queue]    = {}
events:    Dict[str, deque]            = {s: deque(maxlen=100) for s in settings.SYMBOLS}

init_locks         = {s: asyncio.Lock() for s in settings.SYMBOLS}
state_locks        = {s: asyncio.Lock() for s in settings.SYMBOLS}
recovery_flags     = {s: asyncio.Event()  for s in settings.SYMBOLS}
reconnect_counts   = {s: 0                for s in settings.SYMBOLS}
last_reconnect_time= {s: 0.0              for s in settings.SYMBOLS}
connect_start_time = {s: 0.0              for s in settings.SYMBOLS}

_http_session: aiohttp.ClientSession = None

# ---------------------------
# GC Pause Measurement
# ---------------------------
def _on_gc_event(phase, info):
    if phase == "start":
        info["_ts"] = time.perf_counter()
    elif phase == "stop" and "_ts" in info:
        gc_pause_hist.observe(time.perf_counter() - info["_ts"])

gc.callbacks.append(_on_gc_event)

# ---------------------------
# HTTP Session Helper
# ---------------------------
async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session

# ---------------------------
# Safe Queue Put
# ---------------------------
async def safe_put(symbol: str, item: Dict[str, Any]):
    q = buffers[symbol]
    t0 = time.perf_counter()
    try:
        q.put_nowait((t0, item))
    except asyncio.QueueFull:
        queue_overflows.labels(symbol).inc()
        logger.warning("queue overflow, dropping oldest", extra={"symbol": symbol})
        await q.get()
        q.put_nowait((t0, item))

# ---------------------------
# Fetch REST Snapshot
# ---------------------------
async def fetch_snapshot(symbol: str) -> Dict[str, Any]:
    session = await get_http_session()
    backoff = 1.0
    for attempt in range(1, 6):
        try:
            params  = {"symbol": symbol, "limit": settings.LIMIT}
            headers = {"X-MBX-APIKEY": settings.API_KEY}
            with snapshot_latency.time():
                async with session.get(
                    settings.REST_ENDPOINT,
                    params=params, headers=headers, timeout=10
                ) as resp:
                    snapshot_last_status.labels(symbol).set(resp.status)
                    if resp.status != 200:
                        snapshot_retries.labels(symbol).inc()
                        logger.error("snapshot HTTP %s", resp.status,
                                     extra={"symbol": symbol})
                        if resp.status == 418:
                            await asyncio.sleep(60)
                            continue
                    resp.raise_for_status()
                    data = await resp.json()
            return {
                "lastUpdateId": data["lastUpdateId"],
                "bids": SortedDict({float(p): float(q) for p, q in data["bids"]}),
                "asks": SortedDict({float(p): float(q) for p, q in data["asks"]})
            }
        except Exception as e:
            snapshot_retries.labels(symbol).inc()
            logger.warning("snapshot fail #%d: %s", attempt, e,
                           extra={"symbol": symbol})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
    raise RuntimeError(f"{symbol}: snapshot failed")

# ---------------------------
# Initialize Order Book
# ---------------------------
async def initialize_book(symbol: str):
    async with init_locks[symbol]:
        q = buffers[symbol]

        if DEBUG:
            logger.debug(f"[init] start initialize_book for {symbol}")

        # 1) 첫 diff
        if DEBUG:
            logger.debug(f"[init] waiting first diff for {symbol}")
        _, first = await q.get()
        if DEBUG:
            logger.debug(f"[init] got first diff: U={first['U']}, u={first['u']}")
        first_U = first["U"]

        # 2–3) snapshot loop
        while True:
            if DEBUG:
                logger.debug(f"[init] fetching snapshot for {symbol}")
            snap = await fetch_snapshot(symbol)
            last_id = snap["lastUpdateId"]
            if DEBUG:
                logger.debug(f"[init] snapshot lastUpdateId={last_id}")
            if last_id < first_U:
                if DEBUG:
                    logger.debug(f"[init] last={last_id} < first_U={first_U}, retry")
                await asyncio.sleep(0.5)
                continue
            break

        # 4) buffer drain
        buffered: List[Dict[str, Any]] = [first]
        if DEBUG:
            logger.debug(f"[init] draining existing buffer for {symbol}")
        while True:
            try:
                _, d = q.get_nowait()
                buffered.append(d)
            except asyncio.QueueEmpty:
                break
        if DEBUG:
            logger.debug(f"[init] drained {len(buffered)} diffs")

        # 5–6) valid diff 찾기
        valid_idx = None
        for i, d in enumerate(buffered):
            if d["u"] <= last_id:
                continue
            if d["U"] <= last_id + 1 <= d["u"]:
                valid_idx = i
                if DEBUG:
                    logger.debug(f"[init] found valid buffered diff idx={i}")
                break

        while valid_idx is None:
            _, d = await q.get()
            if DEBUG:
                logger.debug(f"[init] checking new diff: U={d['U']}, u={d['u']}")
            if d["u"] > last_id and d["U"] <= last_id + 1 <= d["u"]:
                buffered.append(d)
                valid_idx = len(buffered) - 1
                if DEBUG:
                    logger.debug(f"[init] found valid new diff idx={valid_idx}")
                break
            if d["u"] > last_id:
                buffered.append(d)

        # 7) apply snapshot+diffs
        if DEBUG:
            logger.debug(f"[init] applying snapshot+diffs for {symbol}")
        async with state_locks[symbol]:
            orderbook[symbol] = {
                "lastUpdateId": last_id,
                "bids": snap["bids"],
                "asks": snap["asks"],
            }
            await apply_diff(symbol, buffered[valid_idx], record_metrics=False)
            if DEBUG:
                logger.debug(f"[init] applied first valid diff, remaining={len(buffered)-valid_idx-1}")
            for d in buffered[valid_idx + 1 :]:
                await apply_diff(symbol, d, record_metrics=False)

        logger.info("initialized at %d", last_id, extra={"symbol": symbol})

# ---------------------------
# Apply Diff
# ---------------------------
async def apply_diff(
    symbol: str, diff: Dict[str, Any], record_metrics: bool = True
):
    if record_metrics:
        diffs_received.labels(symbol).inc()
    async with state_locks[symbol]:
        state = orderbook.get(symbol)
        if state is None:
            return
        u, U = diff["u"], diff["U"]
        last = state["lastUpdateId"]
        if u <= last:
            return
        if U > last + 1:
            gap_size = U - (last + 1)
            gap_size_hist.labels(symbol).observe(gap_size)
            if not recovery_flags[symbol].is_set():
                recovery_flags[symbol].set()
                recoveries_total.labels(symbol).inc()
                logger.error("gap detected, U>%d", last + 1,
                             extra={"symbol": symbol})
                asyncio.create_task(_recover(symbol))
            return
        start = time.perf_counter()
        for side, book_side in (("b", state["bids"]), ("a", state["asks"])):
            for p_str, q_str in diff[side]:
                price, qty = float(p_str), float(q_str)
                if qty == 0:
                    book_side.pop(price, None)
                else:
                    book_side[price] = qty
        state["lastUpdateId"] = u
        book_last_update.labels(symbol).set(u)
        if record_metrics:
            process_latency.labels(symbol).observe(time.perf_counter() - start)

# ---------------------------
# Recover from Gap
# ---------------------------
async def _recover(symbol: str):
    try:
        await initialize_book(symbol)
        recovery_success.labels(symbol).inc()
    except Exception:
        recovery_fail.labels(symbol).inc()
    finally:
        recovery_flags[symbol].clear()

# ---------------------------
# Connection Manager
# ---------------------------
class ConnectionManager:
    """Single WS stream for all symbols, dispatch per-symbol."""
    def __init__(self):
        streams = "/".join(f"{s.lower()}@depth@100ms" for s in settings.SYMBOLS)
        self.url = f"{settings.WS_ENDPOINT}?streams={streams}"
        self.tasks: List[asyncio.Task] = []

    async def start(self):
        for s in settings.SYMBOLS:
            buffers[s] = asyncio.Queue(maxsize=settings.QUEUE_MAXSIZE)
        self.tasks.append(asyncio.create_task(self._run()))

    async def _run(self):
        backoff = 1.0
        while True:
            try:
                logger.info("connecting combined WS")
                async with websockets.connect(self.url, ping_interval=30, ping_timeout=10) as ws:
                    buffer_task = asyncio.create_task(self._buffer_loop(ws))
                    for s in settings.SYMBOLS:
                        await initialize_book(s)
                    process_task = asyncio.create_task(self._process_loop())
                    await asyncio.gather(buffer_task, process_task)
            except Exception:
                for s in settings.SYMBOLS:
                    reconnect_counts[s] += 1
                    ws_reconnect_count.labels(s).set(reconnect_counts[s])
                    last_reconnect_time[s] = time.time()
                    ws_connected.labels(s).set(0)
                logger.exception("WS error, reconnect in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _buffer_loop(self, ws):
        while True:
            raw = await ws.recv()
            msg = orjson.loads(raw)
            data = msg.get("data", {})
            sym = data.get("s")
            if DEBUG:
                logger.debug(f"[buffer_loop] recv diff for {sym}: U={data.get('U')}, u={data.get('u')}")
            if sym in buffers:
                events[sym].append(data)
                await safe_put(sym, data)

    async def _process_loop(self):
        if DEBUG:
            logger.debug("[process_loop] starting diff processing")
        while True:
            # **변경된 부분: 큐에 남은 모든 diff를 즉시 소진**
            for sym in settings.SYMBOLS:
                q = buffers[sym]
                while True:
                    try:
                        t0, item = q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    queue_latency.labels(sym).observe(time.perf_counter() - t0)
                    await apply_diff(sym, item)
            await asyncio.sleep(0)

# ---------------------------
# System Monitor
# ---------------------------
async def monitor_system():
    proc = psutil.Process()
    while True:
        try:
            cpu = proc.cpu_percent(None)
            mem = proc.memory_info().rss
            for s in settings.SYMBOLS:
                process_cpu.labels(s).set(cpu)
                process_mem.labels(s).set(mem)
                uptime.labels(s).set(time.perf_counter() - connect_start_time.get(s, 0))
                buffer_size.labels(s).set(buffers[s].qsize())
            await asyncio.sleep(10)
        except Exception:
            logger.exception("monitor_system error")
            await asyncio.sleep(10)

# ---------------------------
# FastAPI Application
# ---------------------------
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    start_http_server(8001)
    asyncio.create_task(ConnectionManager().start())
    asyncio.create_task(monitor_system())

@app.on_event("shutdown")
async def on_shutdown():
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    if _http_session and not _http_session.closed:
        await _http_session.close()
    listener.stop()

@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    return {"ready": all(s in orderbook for s in settings.SYMBOLS)}

@app.get("/state/{symbol}")
async def state(symbol: str):
    if symbol not in orderbook:
        raise HTTPException(404, "Unknown symbol")
    st = orderbook[symbol]
    return {
        "lastUpdateId": st["lastUpdateId"],
        "bids": len(st["bids"]), "asks": len(st["asks"]),
        "recovering": recovery_flags[symbol].is_set(),
        "buffer_size": buffers[symbol].qsize(),
        "reconnects": reconnect_counts[symbol],
        "last_reconnect": last_reconnect_time[symbol]
    }

@app.get("/state/{symbol}/snapshot_top")
async def snapshot_top(symbol: str, levels: int = 10):
    if symbol not in orderbook:
        raise HTTPException(404, "Unknown symbol")
    st = orderbook[symbol]
    return {
        "bids": list(st["bids"].items())[-levels:],
        "asks": list(st["asks"].items())[:levels]
    }

@app.get("/state/{symbol}/recent-diffs")
async def recent_diffs(symbol: str, limit: int = 10):
    if symbol not in buffers:
        raise HTTPException(404, "Unknown symbol")
    return {"recent_diffs": list(buffers[symbol]._queue)[-limit:]}

@app.get("/debug/{symbol}/events")
async def debug_events(symbol: str):
    if symbol not in events:
        raise HTTPException(404, "Unknown symbol")
    return {"events": list(events[symbol])}

@app.get("/debug/metrics")
async def debug_metrics():
    return Response(REGISTRY.generate_latest(), media_type="text/plain")

@app.post("/admin/loglevel")
async def set_loglevel(request: Request):
    body = await request.json()
    level = body.get("level", "").upper()
    if level not in logging._nameToLevel:
        raise HTTPException(400, "Invalid level")
    logging.getLogger().setLevel(logging._nameToLevel[level])
    return {"level": level}

@app.post("/admin/config")
async def update_config(request: Request):
    """Dynamically adjust config: LIMIT, INIT_TIMEOUT, QUEUE_MAXSIZE."""
    body = await request.json()
    for key in ("LIMIT", "INIT_TIMEOUT", "QUEUE_MAXSIZE"):
        if key in body:
            setattr(settings, key, int(body[key]))
    return {
        "LIMIT": settings.LIMIT,
        "INIT_TIMEOUT": settings.INIT_TIMEOUT,
        "QUEUE_MAXSIZE": settings.QUEUE_MAXSIZE
    }

if __name__ == "__main__":
    uvicorn.run("steam_binance:app", host="0.0.0.0", port=8000)
