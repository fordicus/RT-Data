r"""................................................................................

How to Use:

	uvicorn backend.app:app --reload

................................................................................

Dependency:

	pip install fastapi==0.115.12
	pip install "uvicorn[standard]==0.34.2"
	pip install pandas==2.2.2

................................................................................

Functionality:

	Provides a FastAPI backend endpoint for serving tick-level trade data
	loaded from CSV files in response to frontend queries.

	Provides a second endpoint that serves order book snapshots aligned
	to tick timestamps, using pre-normalized DOM data parsed from NDJSON.

	Handles CORS to enable cross-origin requests from a web-based frontend.

................................................................................

IO Structure:

	Input:
		GET /api/tick?symbol=UNIUSDC&date=2025-05-17
			- symbol: asset symbol (default: UNIUSDC)
			- date: ISO-style date string (default: 2025-05-17)

		GET /api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1715883422.0
			- symbol: asset symbol (default: UNIUSDC)
			- date: ISO-style date string (default: 2025-05-17)
			- time: float UNIX timestamp in seconds

	Output:
		/api/tick → JSON array of ticks:
			[
				{ "time": float, "value": float, "side": str, "volume": float },
				...
			]

		/api/orderbook → JSON object:
			{ "time": float, "DOM": "N/A" | { "a": [...], "b": [...] } }

................................................................................

Local Test (DO NOT DELETE, ChatGPT):
			
	curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" -o dump_tick.json
	curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747525846.066" -o dump_dom.json
	
	Location of execution and DOM data
		tick_path = f"data/{symbol}_{date}.csv"
		dom_path  = f"data/{date}_{symbol}_ob200.data"

................................................................................"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.loader import (
	load_trades,
	load_orderbook,
	align_orderbook_to_ticks
)


app = FastAPI()


# Enable CORS for frontend development
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"]
)


# Global caches for tick, orderbook, and alignment (by symbol)
tick_cache      = {}
orderbook_cache = {}
aligned_cache   = {}


@app.on_event("startup")
def preload_data():
	"""
	Preload .csv and .data files into memory at server startup.
	Only for symbol="UNIUSDC" and date="2025-05-17"
	"""
	symbol = "UNIUSDC"
	date   = "2025-05-17"

	tick_path = f"data/{symbol}_{date}.csv"
	dom_path  = f"data/{date}_{symbol}_ob200.data"

	# Load and cache CSV + DOM data
	tick_cache[symbol]      = load_trades(tick_path)
	orderbook_cache[symbol] = load_orderbook(dom_path)

	# Align once, cache result
	aligned_cache[symbol] = align_orderbook_to_ticks(
		tick_cache[symbol],
		orderbook_cache[symbol]
	)


@app.get("/api/tick")
def get_tick_data(
	symbol: str = "UNIUSDC",
	date: str   = "2025-05-17"
):
	"""
	Serve tick-level trade data from CSV as JSON records.
	"""
	df = tick_cache.get(symbol)

	if df is None:
		raise HTTPException(500, "Tick data not preloaded")

	return df.to_dict(orient="records")


@app.get("/api/orderbook")
def get_orderbook_snapshot(
	symbol: str = "UNIUSDC",
	date: str   = "2025-05-17",
	time: float = Query(...)
):
	"""
	Serve DOM snapshot nearest to given tick timestamp.

	Returns:
		- DOM snapshot at closest past ts ≤ given time
		- or "N/A" if no such snapshot exists
	"""
	aligned = aligned_cache.get(symbol)

	if aligned is None:
		raise HTTPException(500, "Orderbook not preloaded")

	dom_snap = aligned.get(time, "N/A")

	return {
		"time": time,
		"DOM" : dom_snap
	}
