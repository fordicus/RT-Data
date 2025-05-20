import pandas as pd

def load_trades(path: str) -> pd.DataFrame:
	"""
	Load and aggregate ByBit trade CSV into sorted DataFrame by dominant side.

	Returns:
		pd.DataFrame with columns: ['time', 'value', 'side', 'volume']
		- time: float (UNIX timestamp in seconds, with milliseconds)
		- value: price (from dominant side)
		- side: 'buy' or 'sell' (majority direction per timestamp)
		- volume: net volume (buy - sell)
	"""
	df = pd.read_csv(path)

	# Drop rpi if present
	df = df.drop(columns=["rpi"], errors="ignore")

	# Rename and reduce columns
	df = df.rename(columns={
		"timestamp": "time",
		"price": "value"
	})[["time", "value", "side", "volume"]]

	# Convert timestamp to seconds as float (preserve ms)
	df["time"] = df["time"] / 1000

	# --- Begin Aggregation ---

	# Group by time and side
	grouped = (
		df.groupby(["time", "side"])
		.agg(
			value=("value", lambda x: (x * df.loc[x.index, "volume"]).sum() / df.loc[x.index, "volume"].sum()),
			volume=("volume", "sum")
		)
		.reset_index()
	)

	# Pivot to wide format by side
	pivoted = grouped.pivot(index="time", columns="side", values=["value", "volume"])
	pivoted.columns = ["_".join(col) for col in pivoted.columns]
	pivoted = pivoted.fillna(0)

	# Compute net volume
	pivoted["net_volume"] = pivoted.get("volume_buy", 0) - pivoted.get("volume_sell", 0)

	# Decide dominant side
	pivoted["side"] = pivoted["net_volume"].apply(lambda x: "buy" if x > 0 else "sell")

	# Choose dominant side price
	def pick_price(row):
		return row["value_buy"] if row["net_volume"] > 0 else row["value_sell"]

	pivoted["value"] = pivoted.apply(pick_price, axis=1)

	# Final output
	result = pivoted[["value", "side", "net_volume"]].reset_index()
	result = result.rename(columns={"net_volume": "volume"})

	# Sort by time
	result = result.sort_values("time").reset_index(drop=True)

	return result