r"""................................................................................

How to Use:
	Import this module and run:
		$ uvicorn steam_binance:app --host 0.0.0.0 --port 8000
		
Temporary Simple Order Book Rendering:
		http://localhost:8000/orderbook/btcusdc
		
....................................................................................

Dependency:
	Python ≥ 3.9
	aiohttp==3.9.5
	websockets==12.0
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
			/state/{symbol}/recent-diffs → recent diffs (if enabled)
			/debug/{symbol}/events	  → raw stream events (for debugging)
		- HTML Endpoint:
			/orderbook/{symbol} → auto-refreshing top-20 bid/ask view
			
....................................................................................
			
Binance Official GitHub Manual:
	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

Binance API Tutorial:
	https://www.binance.com/en/support/faq/detail/360002502072

API Management:
	https://www.binance.com/en/my/settings/api-management
	
....................................................................................
	
Note:

	Tardis.dev (https://tardis.dev/#pricing) offers comprehensive
	historical order book (L2) and trade data across multiple exchanges,
	but, for example, Derivatives Exchanges annual subscription costs circa
	$15,000/year. As a practical alternative, this project streams live Binance
	L2 (depth20) data at 100ms intervals for real-time analysis and lightweight
	historical collection.
	
....................................................................................

TODO:
	
	- Downstream also execution datafeed to collect historical OHLCV data.
	- Accumulate the data stream in a proper way.
	
................................................................................"""


import asyncio
import json
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import websockets

# Initialize FastAPI instance
app = FastAPI()

# Set up a logger compatible with Uvicorn logging convention
logger = logging.getLogger("uvicorn.error")

# Register Jinja2 template engine (template directory is relative to this file)
templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------------------------------
# Configuration Section
# ------------------------------------------------------------------------------

# Symbol list to subscribe to via WebSocket (all lowercase required by Binance)
SYMBOLS = ["btcusdc"]  # Extendable to multiple pairs: e.g., ["btcusdc", "ethusdc"]

# Compose the combined stream URL for depth20 updates every 100ms
STREAMS_PARAM = "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

# Local in-memory order book snapshot for each symbol
# Example structure:
#   {
#	   "lastUpdateId": 123456,
#	   "eventTime": 1650000000000,
#	   "bids": [[price1, qty1], ..., [price20, qty20]],
#	   "asks": [[price1, qty1], ..., [price20, qty20]]
#   }
book_state: dict[str, dict] = {}

# Internal flag to mark readiness after the first message is received
ready_event = asyncio.Event()

# ------------------------------------------------------------------------------
# WebSocket Consumer Task
# ------------------------------------------------------------------------------

async def consume_order_books() -> None:
	"""
	Connects to Binance's combined WebSocket stream and maintains an up-to-date
	in-memory snapshot of the order book for all subscribed symbols.

	Retries up to 5 times with exponential backoff on connection failures.
	Marks the application as "ready" after first valid update.
	"""
	for attempt in range(1, 6):
		try:
			# Establish persistent WebSocket connection
			async with websockets.connect(WS_URL) as ws:
				logger.info(f"Connected to {WS_URL} (depth20@100ms)")

				# Continuously consume messages from Binance
				async for raw in ws:
					msg = json.loads(raw)

					# 1) Parse stream metadata to determine the symbol
					stream = msg.get("stream", "")
					symbol = stream.split("@", 1)[0].lower()
					if symbol not in SYMBOLS:
						continue  # Skip unknown/unsubscribed symbols

					# 2) Extract book data from message payload
					data = msg.get("data", {})
					last_update = data.get("lastUpdateId")
					if last_update is None:
						continue  # Unexpected message format

					bids = data.get("bids", [])
					asks = data.get("asks", [])

					# 3) Convert & cache parsed order book state in memory
					book_state[symbol] = {
						"lastUpdateId": last_update,
						"eventTime": int(time.time() * 1_000),  # arrival timestamp (ms)
						"bids": [[float(p), float(q)] for p, q in bids],
						"asks": [[float(p), float(q)] for p, q in asks],
					}

					# 4) Notify system readiness after first valid message
					if not ready_event.is_set():
						ready_event.set()

		except Exception as e:
			logger.error(f"WebSocket error (attempt {attempt}): {e}")
			await asyncio.sleep(2 ** attempt)  # Exponential backoff on failure

	# If all retry attempts fail, service is considered unavailable
	logger.critical("Failed to connect to Binance after multiple attempts.")

# ------------------------------------------------------------------------------
# FastAPI Lifecycle Hook: Startup Event
# ------------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
	"""
	FastAPI lifecycle hook that launches the WebSocket consumer as a background task.
	Blocks request handling until the first message is received.
	"""
	asyncio.create_task(consume_order_books())
	await ready_event.wait()
	logger.info("Order book consumer is ready.")

# ------------------------------------------------------------------------------
# Healthcheck Endpoints (Kubernetes/LB readiness/liveness probes)
# ------------------------------------------------------------------------------

@app.get("/health/live")
async def health_live():
	"""
	Liveness probe.

	Returns 200 OK as long as the process is running, regardless of connection status.
	"""
	return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
	"""
	Readiness probe.

	Returns 200 OK if the WebSocket consumer has received at least one valid update.
	Otherwise, returns 503 Service Unavailable.
	"""
	if ready_event.is_set():
		return {"status": "ready"}
	raise HTTPException(status_code=503, detail="not ready")

# ------------------------------------------------------------------------------
# Order Book Data Endpoint (API)
# ------------------------------------------------------------------------------

@app.get("/state/{symbol}")
async def get_order_book(symbol: str):
	"""
	Return the latest partial order book (top 20 bids & asks) as JSON.

	Args:
		symbol (str): ticker pair in lowercase (e.g. 'btcusdc').

	Returns:
		JSONResponse: {
		  "lastUpdateId": int,
		  "eventTime": int,
		  "bids": [[price, qty], …],
		  "asks": [[price, qty], …]
		}

	Raises:
		HTTPException 404 if symbol not in memory.
	"""
	symbol = symbol.lower()
	if symbol not in book_state:
		raise HTTPException(status_code=404, detail="symbol not found")
	return JSONResponse(content=book_state[symbol])

# ------------------------------------------------------------------------------
# HTML Rendering Endpoint for Order Book Visualization
# ------------------------------------------------------------------------------

@app.get("/orderbook/{symbol}", response_class=HTMLResponse)
async def orderbook_ui(request: Request, symbol: str):
	"""
	Serves a human-readable HTML visualization of the current order book
	for the given symbol (with 20 best bid/ask entries).
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

# ------------------------------------------------------------------------------
# Script Entrypoint (development only)
# ------------------------------------------------------------------------------

if __name__ == "__main__":
	"""
	Development entrypoint for running the FastAPI app with Uvicorn.
	"""
	import uvicorn
	uvicorn.run("steam_binance:app", host="0.0.0.0", port=8000)
