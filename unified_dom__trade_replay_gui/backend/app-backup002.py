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
	curl "http://localhost:8000/api/orderbook?symbol=UNIUSDC&date=2025-05-17&time=1747442146.179" -o dump_dom.json
	
	Location of execution and DOM data
		tick_path = f"data/{symbol}_{date}.csv"
		dom_path  = f"data/{date}_{symbol}_ob200.data"

................................................................................"""

from fastapi import FastAPI, Query
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


@app.get("/api/tick")
def get_tick_data(
	symbol: str = "UNIUSDC",
	date: str   = "2025-05-17"
):
	"""
	Serve tick-level trade data from CSV as JSON records.
	"""
	file_path = f"data/{symbol}_{date}.csv"

	# Load execution data from CSV
	df = load_trades(file_path)

	# Return as list of dicts
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
	# Load execution and DOM data
	tick_path = f"data/{symbol}_{date}.csv"
	dom_path  = f"data/{date}_{symbol}_ob200.data"

	df_ticks = load_trades(tick_path)
	dom_dict = load_orderbook(dom_path)

	# Align and lookup requested time
	aligned  = align_orderbook_to_ticks(df_ticks, dom_dict)
	dom_snap = aligned.get(time, "N/A")

	return {
		"time": time,
		"DOM" : dom_snap
	}
