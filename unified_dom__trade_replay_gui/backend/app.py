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

	Handles CORS to enable cross-origin requests from a web-based frontend.

................................................................................

IO Structure:

	Input:
		GET /api/tick?symbol=UNIUSDC&date=2025-05-17
			- symbol: asset symbol (default: UNIUSDC)
			- date: ISO-style date string (default: 2025-05-17)

	Output:
		JSON array of records with the structure:
		[
			{
				"time": float (in seconds),
				"value": float,
				"side": str,
				"volume": float
			},
			...
		]

................................................................................"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from backend.loader import load_trades


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
	date: str = "2025-05-17"
):
	"""
	Serve tick-level trade data from CSV as JSON records.
	"""
	file_path = f"data/{symbol}_{date}.csv"

	# Load DataFrame using the loader module
	df = load_trades(file_path)

	# Return as list of dicts (records)
	return df.to_dict(orient="records")
