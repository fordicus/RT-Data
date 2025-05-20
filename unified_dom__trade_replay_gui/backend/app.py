from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from backend.loader import load_trades

app = FastAPI()

# Allow frontend cross-origin calls
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"]
)

@app.get("/api/tick")
def get_tick_data(symbol: str = "UNIUSDC", date: str = "2025-05-17"):
	"""
	Returns tick data as a list of {time, value, side, volume} dictionaries.
	"""
	file_path = f"data/{symbol}_{date}.csv"
	df = load_trades(file_path)
	return df.to_dict(orient="records")