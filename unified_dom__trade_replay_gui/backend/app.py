r"""................................................................................
MODULE OVERVIEW:

	This module launches a FastAPI-based backend serving historical ByBit
	market data for interactive DOM replay. Data is accessed from local files
	and served to the frontend via REST API.

................................................................................
ARCHITECTURE:

	↪ app.py (this file)
		- Exposes two endpoints:
			• /api/tick       → tick data (from .csv)
			• /api/orderbook  → DOM snapshot (from .data)

	↪ backend/loader.py
		- Loads and aligns tick + DOM data at startup
		- Populates in-memory caches (tick_cache, orderbook_cache, aligned_cache)

	↪ frontend/main.ts
		- Requests data using REST endpoints
		- Renders:
			• tick chart (left pane)
			• DOM canvas + mirrored tooltip (right pane)

................................................................................
RUNTIME & DEV SETUP:

	1. Dependencies:
		Python 3.9.19
		pip install fastapi==0.115.12
		pip install pandas==2.2.2
		pip install "uvicorn[standard]==0.34.2"

	2. Launch backend:
		uvicorn backend.app:app --reload

	3. Launch frontend:
		cd frontend && npm run dev

................................................................................
RUNTIME URLS:

	• FastAPI tick data:
	    http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17

	• FastAPI order book:
	    http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17
	                                             &time=1747524319.016

	• Frontend (Vite dev server):
	    http://localhost:5173

	• Utility Files (in project root):
	    • local_frontend.url – opens frontend in browser
	    • test_cmd.bat        – unified launcher for both backend + frontend

................................................................................
DATA FLOW & STORAGE:

	Hardcoded test case:
		symbol = "UNIUSDC"
		date   = "2025-05-17"

	Input files:
		• data/UNIUSDC_2025-05-17.csv
		• data/2025-05-17_UNIUSDC_ob200.data

	Parsed using:
		- load_trades(), load_orderbook()
	Aligned using:
		- align_orderbook_to_ticks()

................................................................................
SAMPLE API CALLS:

	curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" \
	     -o dump_tick.json

	curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17\
	     &time=1747525846.066" -o dump_dom.json

................................................................................
📚 DATA FORMAT REFERENCE:

	- 📘 OrderBook Format (bybit_orderbook_format.md)
	    → Tick-level DOM snapshots and deltas (.data)

	- 📙 Execution Format (bybit_execution_format.md)
	    → Trade history with RPI flags (.csv)

	- 🔗 ByBit Official Explanation:
	    https://bybit-exchange.github.io/docs/tax/explain

................................................................................"""

# Import FastAPI core components:
# - FastAPI: the main app object
# - Query: defines required query parameters
# - HTTPException: used to return error messages to client
from fastapi import FastAPI, Query, HTTPException

# Import a helper to allow requests from another browser tab (e.g., frontend)
# This is needed when the client and server use different ports (e.g., 5173 → 8000)
from fastapi.middleware.cors import CORSMiddleware

# Import data loaders from local file
# These convert .csv and .data files into Python data structures
from backend.loader import (
	load_trades,              # Load tick-level trade data (CSV)
	load_orderbook,           # Load DOM snapshots (NDJSON)
	align_orderbook_to_ticks  # Align DOM snapshots to trade times
)

# Create the FastAPI app (this becomes the API server)
app = FastAPI()

# Allow the frontend (running in browser) to fetch data from this server
# This prevents browser-side blocking when ports differ (so-called cross-origin access)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"]
)

# In-memory cache dictionaries (no database)
# These are filled once at startup and reused for all incoming requests
tick_cache      = {}  # Holds loaded tick DataFrames, keyed by symbol
orderbook_cache = {}  # Holds raw DOM snapshots per symbol
aligned_cache   = {}  # Holds DOM-aligned-to-tick mapping: { timestamp → DOM }
                     # Used for efficient lookup by frontend


@app.on_event("startup")
def preload_data():
	"""
	Preload .csv and .data files into memory when server starts.

	This step avoids repeated disk reads during requests.
	"""
	symbol = "UNIUSDC"
	date   = "2025-05-17"

	tick_path = f"data/{symbol}_{date}.csv"
	dom_path  = f"data/{date}_{symbol}_ob200.data"

	# Read CSV and NDJSON files once
	tick_cache[symbol]      = load_trades(tick_path)
	orderbook_cache[symbol] = load_orderbook(dom_path)

	# Align orderbook snapshots to tick timestamps for fast lookup
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
	Return full tick data (price, side, volume, etc.) as a list of JSON records.
	Client specifies symbol and date via query parameters.
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
	Look up and return the DOM snapshot aligned to the given timestamp.
	Returns "N/A" if no matching timestamp exists in prealigned cache.
	"""
	aligned = aligned_cache.get(symbol)

	if aligned is None:
		raise HTTPException(500, "Orderbook not preloaded")

	dom_snap = aligned.get(time, "N/A")

	return {
		"time": time,
		"DOM" : dom_snap
	}
