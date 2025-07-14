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

		📁 Tick+DOM Pair Loader via Filename Convention
			- Autodetects *.csv + *.data pair from ./data/ folder at startup
			- Extracts {symbol, date} from filename patterns
			- Ensures both files agree on symbol (e.g., "UNIUSDC")

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

	• FastAPI tick data example:
	    http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17

	• FastAPI order book example:
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

	📦 Plan04 (autodetect mode):
		- Relies on a single valid .csv and .data pair in ./data/
		- Enforces filename conventions to determine the instrument

................................................................................
SAMPLE API CALLS:

	curl "http://localhost:8000/api/tick?symbol=UNIUSDC&date=2025-05-17" -o dump_tick.json
	curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747525846.066" -o dump_dom.json

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

import os
import sys
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.loader import (
	load_trades,
	load_orderbook,
	align_orderbook_to_ticks
)

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"]
)

tick_cache      = {}
orderbook_cache = {}
aligned_cache   = {}


@app.on_event("startup")
def preload_data():
	"""
	📦 Plan04: Autoload data files from `./data/` on FastAPI startup.

	Used when launching the backend via _run_reply_gui.bat without CLI arguments.
	This function ensures a unified loading behavior that matches frontend requests.

	🔒 Assumptions:
	• Directory `./data/` exists under the current working directory.
	• It contains exactly ONE `.csv` and ONE `.data` file.
	• The filenames encode the instrument symbol to allow cross-checking:
	    - Tick CSV     : {SYMBOL}_YYYY-MM-DD.csv
	    - DOM Snapshot: YYYY-MM-DD_{SYMBOL}_ob200.data
	• The `SYMBOL` part must match across both filenames.

	🚫 Program exits immediately if:
	• Directory `./data/` is missing
	• Multiple or zero files of either type are present
	• SYMBOL mismatch between the two files
	"""
	
	# Compute absolute path to ./data/ subdirectory (relative to script location)
	data_dir = os.path.join(os.getcwd(), "data")

	# ✅ Existence check: folder must exist
	if not os.path.isdir(data_dir):
		print(f"[ERROR] Directory not found: {data_dir}")
		sys.exit(1)

	# List all filenames in data/ and filter by extensions
	files = os.listdir(data_dir)
	csvs  = [f for f in files if f.endswith(".csv")]
	datas = [f for f in files if f.endswith(".data")]

	# ✅ Ensure exactly one file of each type
	if len(csvs) != 1 or len(datas) != 1:
		print("[ERROR] data/ must contain exactly ONE .csv and ONE .data file.")
		sys.exit(1)

	csv_file  = csvs[0]
	data_file = datas[0]

	# Extract symbols from each file name by parsing their filename format
	try:
		symbol_csv  = csv_file.split("_")[0]   # e.g., UNIUSDC_2025-05-17.csv → UNIUSDC
		symbol_data = data_file.split("_")[1]  # e.g., 2025-05-17_UNIUSDC_ob200.data → UNIUSDC
	except IndexError:
		print("[ERROR] Failed to extract symbol from filenames.")
		sys.exit(1)

	# ✅ Ensure symbols from both files match
	if symbol_csv != symbol_data:
		print(f"[ERROR] Symbol mismatch: {symbol_csv} ≠ {symbol_data}")
		sys.exit(1)

	# Final resolved values for loading
	symbol    = symbol_csv
	csv_path  = os.path.join(data_dir, csv_file)
	data_path = os.path.join(data_dir, data_file)

	# 🧠 Log the resolved files to backend console (for developer inspection)
	print(f"[INFO] Loading Tick CSV : {csv_path}")
	print(f"[INFO] Loading DOM Data  : {data_path}")
	print(f"[INFO] Using Symbol      : {symbol}")

	# 🔁 Load, aggregate, and align data once during server startup
	tick_cache[symbol]      = load_trades(csv_path)
	orderbook_cache[symbol] = load_orderbook(data_path)
	aligned_cache[symbol]   = align_orderbook_to_ticks(
		tick_cache[symbol],
		orderbook_cache[symbol]
	)

@app.get("/api/meta")
def get_loaded_meta():
	"""
	📡 API: /api/meta

	Return the currently loaded symbol and trading date.
	Used by the frontend to dynamically construct backend data fetch URLs.

	📤 Response Format:
	{
	    "symbol": "UNIUSDC",
	    "date"  : "2025-05-17"
	}

	📌 Motivation:
	- This decouples frontend logic from hardcoded filenames or paths.
	- Enables flexible visualization for any {symbol, date} pair
	  that has been auto-loaded via Plan04 preload logic.
	- Ensures frontend chart labels, tooltip content, and URL templates
	  remain consistent with backend state.

	🔒 Error Conditions:
	- If no tick data is present in memory (empty `tick_cache`)
	  → returns HTTP 500.
	- If the `time` column is missing in the DataFrame
	  → returns HTTP 500 (malformed or corrupted CSV).
	"""

	# 🛑 Ensure tick data was preloaded
	if not tick_cache:
		raise HTTPException(500, "No tick data loaded.")

	# ✅ Extract loaded symbol (only one expected under Plan04)
	symbol = list(tick_cache.keys())[0]
	df     = tick_cache[symbol]

	# 🛑 Defensive check: 'time' column must exist in tick data
	if "time" not in df.columns:
		raise HTTPException(500, "Malformed tick data.")

	# 🧠 Extract first timestamp to determine the trading date
	first_ts = df["time"].iloc[0]
	date_str = pd.to_datetime(first_ts, unit='s').strftime("%Y-%m-%d")

	# ✅ Return the resolved metadata for frontend use
	return {
		"symbol": symbol,
		"date"  : date_str
	}

@app.get("/api/tick")
def get_tick_data(
	symbol: str = "UNIUSDC",
	date: str   = "2025-05-17"
):
	"""
	📡 API: /api/tick

	Return full tick-by-tick data as a list of JSON records.

	🧠 Usage Context:
	- Frontend fetches this data using `/api/meta`-provided symbol/date.
	- Used to render price chart and tooltips.

	📥 Query Parameters (from frontend):
	  - symbol : str  (e.g., "UNIUSDC")
	  - date   : str  (e.g., "2025-05-17")

	📤 Response Format (list of objects):
	  [
		{
		  "time"  : float  (UNIX timestamp in seconds),
		  "value" : float  (execution price),
		  "volume": float  (signed trade volume),
		  "side"  : str    ("buy" or "sell")
		},
		...
	  ]

	📌 Note:
	  This endpoint currently assumes data is preloaded during startup.
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
	📡 API: /api/orderbook

	Return DOM (Depth of Market) snapshot aligned to the requested timestamp.

	🧠 Usage Context:
	- Called on hover or click in the frontend for visualizing orderbook depth.

	📥 Query Parameters:
	  - symbol : str   (e.g., "UNIUSDC")
	  - date   : str   (e.g., "2025-05-17")
	  - time   : float (UNIX timestamp in seconds, ms precision)

	📤 Response Format:
	  {
		"time": float,
		"DOM" : dict | str  // {"a": [...], "b": [...]} or "N/A"
	  }

	📌 Notes:
	- If the timestamp has no matching DOM snapshot (e.g., before first DOM tick),
	  the string `"N/A"` is returned.
	"""
	aligned = aligned_cache.get(symbol)

	if aligned is None:
		raise HTTPException(500, "Orderbook not preloaded")

	dom_snap = aligned.get(time, "N/A")

	return {
		"time": time,
		"DOM" : dom_snap
	}