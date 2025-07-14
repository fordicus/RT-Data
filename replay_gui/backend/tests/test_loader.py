import pytest
from backend.loader import load_trades

def test_load_trades_basic():
	df = load_trades("data/UNIUSDC_2025-05-17.csv")

	assert df.shape[0] > 0
	assert all(col in df.columns for col in ["time", "value", "side", "volume"])
	assert df["time"].is_monotonic_increasing
	assert df["side"].isin(["buy", "sell"]).all()
