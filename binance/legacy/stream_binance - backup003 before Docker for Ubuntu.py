# stream_binance.py

r"""................................................................................

How to Use:
	Import this module and run:
		$ uvicorn stream_binance:app --host 0.0.0.0 --port 8000

Temporary Simple Order Book Rendering:
		http://localhost:8000/orderbook/btcusdc

................................................................................

Dependency:
	Python ≥ 3.9
	aiohttp==3.9.5
	websockets==11.0.3
	orjson==3.10.1
	sortedcontainers==2.4.0
	pydantic==2.7.1
	pydantic-settings>=2.0.0
	fastapi==0.111.0
	prometheus_client==0.20.0
	uvicorn==0.30.1
	psutil==5.9.8
	jinja2==3.1.3

Functionality:
	Stream Binance partial order book (depth20 @100ms) via a combined websocket subscription.
	Maintain an in-memory snapshot of the top 20 bids and asks for each symbol.
	Expose both machine-readable JSON endpoints and a lightweight HTML UI for real-time visualization.

IO Structure:
	Inputs:
		- Binance websocket stream:
		  wss://stream.binance.com:9443/stream?streams={symbol}@depth20@100ms
	Outputs:
		- JSON Endpoints:
			/health/live	   → liveness probe
			/health/ready	  → readiness after first stream message
			/state/{symbol}	→ current order book state
		- HTML Endpoint:
			/orderbook/{symbol} → auto-refreshing top-20 bid/ask view

................................................................................

Binance Official GitHub Manual:
	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

................................................................................
"""

import asyncio
import json
import logging
import time
import random
import os
import zipfile
import shutil
import threading
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import websockets

# ───────────────────────────────
# ⚙️ Application + Template Setup
# ───────────────────────────────
app = FastAPI()
logger = logging.getLogger("uvicorn.error")
templates = Jinja2Templates(directory="templates")

# ───────────────────────────────
# ⚙️ Configuration from .conf
# ───────────────────────────────
CONFIG_PATH = "get_binance_chart.conf"
CONFIG = {}

def load_config(conf_path: str):
	try:
		with open(conf_path, 'r', encoding='utf-8') as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				line = line.split("#", 1)[0].strip()
				if "=" in line:
					key, val = line.split("=", 1)
					CONFIG[key.strip()] = val.strip()
	except Exception as e:
		logger.error(f"Failed to load config from {conf_path}: {e}")

load_config(CONFIG_PATH)

SYMBOLS = [s.lower() for s in CONFIG.get("SYMBOLS", "").split(",") if s.strip()]
if not SYMBOLS:
	raise RuntimeError("No SYMBOLS loaded from config.")
	
STREAMS_PARAM = "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

BASE_BACKOFF = int(CONFIG.get("BASE_BACKOFF", 2))
MAX_BACKOFF = int(CONFIG.get("MAX_BACKOFF", 30))
RESET_CYCLE_AFTER = int(CONFIG.get("RESET_CYCLE_AFTER", 7))
LOB_DIR = CONFIG.get("LOB_DIR", "./data/binance/orderbook/")
SAVE_INTERVAL_MIN = int(CONFIG.get("SAVE_INTERVAL_MIN", 1440))
PURGE_ON_DATE_CHANGE = int(CONFIG.get("PURGE_ON_DATE_CHANGE", 1))

if SAVE_INTERVAL_MIN > 1440:
	raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

os.makedirs(LOB_DIR, exist_ok=True)

# ───────────────────────────────
# 📦 Runtime Order Book Storage
# ───────────────────────────────
book_state: dict[str, dict] = {}
ready_event = asyncio.Event()
save_queue = asyncio.Queue()
file_handles: dict[str, tuple[str, asyncio.StreamWriter]] = {}

# ───────────────────────────────
# 🧰 Utility Functions
# ───────────────────────────────
def get_file_suffix(interval_min: int) -> str:
	now = datetime.utcnow()
	if interval_min >= 1440:
		return now.strftime("%Y-%m-%d")
	else:
		return now.strftime("%Y-%m-%d_%H-%M")

def get_date_from_suffix(suffix: str) -> str:
	return suffix.split("_")[0]

def zip_and_remove(src_path: str):
	if os.path.exists(src_path):
		zip_path = src_path.replace(".jsonl", ".zip")
		with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.write(src_path, arcname=os.path.basename(src_path))
		os.remove(src_path)

def merge_day_zips_to_single_jsonl(symbol: str, day_str: str, base_dir: str, purge: bool = True):
	tmp_dir = os.path.join(base_dir, "temporary", f"{symbol.upper()}_orderbook_{day_str}")
	merged_path = os.path.join(base_dir, f"{symbol.upper()}_orderbook_{day_str}.jsonl")
	if not os.path.isdir(tmp_dir):
		return

	with open(merged_path, "w", encoding="utf-8") as fout:
		for zip_file in sorted(os.listdir(tmp_dir)):
			if not zip_file.endswith(".zip"):
				continue
			zip_path = os.path.join(tmp_dir, zip_file)
			with zipfile.ZipFile(zip_path, "r") as zf:
				for name in zf.namelist():
					with zf.open(name) as f:
						for line in f:
							fout.write(line.decode("utf-8"))

	final_zip = merged_path.replace(".jsonl", ".zip")
	with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
		zf.write(merged_path, arcname=os.path.basename(merged_path))
	os.remove(merged_path)
	if purge:
		shutil.rmtree(tmp_dir)

def merge_all_symbols_for_day(symbols: list[str], day_str: str):
	for symbol in symbols:
		merge_day_zips_to_single_jsonl(symbol, day_str, LOB_DIR, purge=(PURGE_ON_DATE_CHANGE == 1))

# ───────────────────────────────
# 📝 Background Task: Save to File
# ───────────────────────────────
async def orderbook_writer():
	while True:
		symbol, snapshot = await save_queue.get()
		suffix = get_file_suffix(SAVE_INTERVAL_MIN)
		day_str = get_date_from_suffix(suffix)
		filename = f"{symbol.upper()}_orderbook_{suffix}.jsonl"

		tmp_dir = os.path.join(LOB_DIR, "temporary", f"{symbol.upper()}_orderbook_{day_str}")
		os.makedirs(tmp_dir, exist_ok=True)
		file_path = os.path.join(tmp_dir, filename)

		last_suffix, writer = file_handles.get(symbol, (None, None))

		if last_suffix and get_date_from_suffix(last_suffix) != day_str:
			threading.Thread(target=merge_all_symbols_for_day, args=(SYMBOLS, get_date_from_suffix(last_suffix))).start()

		if last_suffix != suffix:
			if writer:
				writer.close()
				zip_and_remove(os.path.join(tmp_dir, f"{symbol.upper()}_orderbook_{last_suffix}.jsonl"))
			writer = open(file_path, "a", encoding="utf-8")
			file_handles[symbol] = (suffix, writer)

		line = json.dumps(snapshot, separators=(",", ":"))
		writer.write(line + "\n")
		writer.flush()

# ───────────────────────────────
# 🔁 WebSocket Consumer with Retry
# ───────────────────────────────
async def consume_order_books() -> None:
	attempt = 0
	while True:
		try:
			async with websockets.connect(WS_URL) as ws:
				logger.info(f"Connected to {WS_URL} (depth20@100ms)")
				attempt = 0

				async for raw in ws:
					msg = json.loads(raw)
					stream = msg.get("stream", "")
					symbol = stream.split("@", 1)[0].lower()
					if symbol not in SYMBOLS:
						continue

					data = msg.get("data", {})
					last_update = data.get("lastUpdateId")
					if last_update is None:
						continue

					bids = data.get("bids", [])
					asks = data.get("asks", [])

					snapshot = {
						"lastUpdateId": last_update,
						"eventTime": int(time.time() * 1_000),
						"bids": [[float(p), float(q)] for p, q in bids],
						"asks": [[float(p), float(q)] for p, q in asks],
					}
					book_state[symbol] = snapshot
					await save_queue.put((symbol, snapshot))

					if not ready_event.is_set():
						ready_event.set()

		except Exception as e:
			attempt += 1
			logger.warning(f"WebSocket error (attempt {attempt}): {e}")
			backoff = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 1)
			if attempt > RESET_CYCLE_AFTER:
				attempt = 3
			logger.warning(f"Retrying in {backoff:.1f} seconds...")
			await asyncio.sleep(backoff)

		finally:
			logger.info("WebSocket connection closed.")

# ───────────────────────────────
# 🚀 Startup Hook
# ───────────────────────────────
@app.on_event("startup")
async def startup_event():
	asyncio.create_task(orderbook_writer())
	asyncio.create_task(consume_order_books())
	await ready_event.wait()
	logger.info(f"Ready. Try [http://localhost:8000/orderbook/{SYMBOLS[0]}]")

# ───────────────────────────────
# 🔍 Healthcheck Endpoints
# ───────────────────────────────
@app.get("/health/live")
async def health_live():
	return {"status": "alive"}

@app.get("/health/ready")
async def health_ready():
	if ready_event.is_set():
		return {"status": "ready"}
	raise HTTPException(status_code=503, detail="not ready")

# ───────────────────────────────
# 🧠 JSON API for Order Book
# ───────────────────────────────
@app.get("/state/{symbol}")
async def get_order_book(symbol: str):
	symbol = symbol.lower()
	if symbol not in book_state:
		raise HTTPException(status_code=404, detail="symbol not found")
	return JSONResponse(content=book_state[symbol])

# ───────────────────────────────
# 👁️ HTML UI for Order Book
# ───────────────────────────────
@app.get("/orderbook/{symbol}", response_class=HTMLResponse)
async def orderbook_ui(request: Request, symbol: str):
	sym = symbol.lower()
	if sym not in book_state:
		raise HTTPException(status_code=404, detail="symbol not found")

	data = book_state[sym]
	bids = data["bids"]
	asks = data["asks"]
	max_len = max(len(bids), len(asks))

	return templates.TemplateResponse(
		"orderbook.html",
		{
			"request": request,
			"symbol": sym,
			"bids": bids,
			"asks": asks,
			"max_len": max_len,
		},
	)

# ───────────────────────────────
# 🧪 Script Entrypoint (dev only)
# ───────────────────────────────
if __name__ == "__main__":
	import uvicorn
	from fastapi import FastAPI

	# 현재 파일 내에서 정의한 app 객체를 직접 넘겨준다
	uvicorn.run(app, host="0.0.0.0", port=8000)