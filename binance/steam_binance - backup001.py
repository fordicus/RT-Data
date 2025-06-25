"""
How to Use:

    Import this module and run with:
	
        uvicorn steam_binance:app --host 0.0.0.0 --port 8000
        uvicorn steam_binance:app --host 0.0.0.0 --port 8000 --log-level debug
		
    Monitor:
        http://localhost:8000/health/live
        http://localhost:8000/health/ready
        http://localhost:8000/state/BTCUSDC
        http://localhost:8000/state/BTCUSDC/recent-diffs
        http://localhost:8000/debug/BTCUSDC/events
		
	Temporary Simple Order Book Rendering:
		http://localhost:8000/orderbook/btcusdc
"""

import asyncio
import json
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import websockets

app = FastAPI()
logger = logging.getLogger("uvicorn.error")

# Initialize Jinja2 templates (expects a "templates/" directory next to this file)
templates = Jinja2Templates(directory="templates")

# --- Configuration ---------------------------------------------------------

# List of symbols to subscribe to (lowercase)
SYMBOLS = ["btcusdc"]  # extend as needed (e.g. ["btcusdc", "ethusdc", ...])

# Build the combined‐stream URL for Partial Book Depth: top 20 levels @100ms
STREAMS_PARAM = "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

# In‐memory store of the latest book for each symbol
# Each entry will look like:
#   {
#     "lastUpdateId": <int>,
#     "eventTime": <int>,
#     "bids": [[price: float, qty: float], … up to 20 entries],
#     "asks": [[price: float, qty: float], … up to 20 entries]
#   }
book_state: dict[str, dict] = {}

# Event to signal that the first websocket message has arrived
ready_event = asyncio.Event()


# --- WebSocket Consumer ----------------------------------------------------

async def consume_order_books() -> None:
    """
    Connect to Binance combined Partial Book Depth streams (depth20@100ms)
    and update the in‐memory order book state on every message.
    """
    # retry loop: use regular for, not async for
    for attempt in range(1, 6):
        try:
            async with websockets.connect(WS_URL) as ws:
                logger.info(f"Connected to {WS_URL} (depth20@100ms)")

                async for raw in ws:
                    msg = json.loads(raw)

                    # 1) extract symbol from the "stream" field
                    stream = msg.get("stream", "")
                    symbol = stream.split("@", 1)[0].lower()
                    if symbol not in SYMBOLS:
                        continue

                    # 2) extract the partial book snapshot
                    data = msg.get("data", {})
                    last_update = data.get("lastUpdateId")
                    if last_update is None:
                        # unexpected message format
                        continue

                    bids = data.get("bids", [])
                    asks = data.get("asks", [])

                    # 3) update in‐memory state
                    book_state[symbol] = {
                        "lastUpdateId": last_update,
                        "eventTime": int(time.time() * 1_000),  # arrival timestamp in ms
                        "bids": [[float(p), float(q)] for p, q in bids],
                        "asks": [[float(p), float(q)] for p, q in asks],
                    }

                    # 4) signal readiness on first valid update
                    if not ready_event.is_set():
                        ready_event.set()

        except Exception as e:
            logger.error(f"WebSocket error (attempt {attempt}): {e}")
            await asyncio.sleep(2 ** attempt)

    logger.critical("Failed to connect to Binance after multiple attempts.")
    # If we exit here, the service will no longer be ready


# --- FastAPI Startup -------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    # Launch the consumer in the background
    asyncio.create_task(consume_order_books())
    # Wait until at least one message arrives
    await ready_event.wait()
    logger.info("Order book consumer is ready.")


# --- Health Endpoints ------------------------------------------------------

@app.get("/health/live")
async def health_live():
    """Always returns alive if the process is running."""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """
    Returns ready once we've successfully connected and received our
    first depth20@100ms message.
    """
    if ready_event.is_set():
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="not ready")


# --- Order Book Endpoint ---------------------------------------------------

@app.get("/state/{symbol}")
async def get_order_book(symbol: str):
    """
    Return the latest partial order book (top 20 bids & asks)
    for the given symbol.
    """
    symbol = symbol.lower()
    if symbol not in book_state:
        raise HTTPException(status_code=404, detail="symbol not found")
    return JSONResponse(content=book_state[symbol])


# --- Order Book UI Endpoint ------------------------------------------------

@app.get("/orderbook/{symbol}", response_class=HTMLResponse)
async def orderbook_ui(request: Request, symbol: str):
    """
    Render a simple HTML page showing the top 20 bids and asks for the symbol.
    """
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


# --- Main Entrypoint -------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("steam_binance:app", host="0.0.0.0", port=8000)
