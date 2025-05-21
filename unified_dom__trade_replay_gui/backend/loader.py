r"""................................................................................

How to Use:

	Called internally via `app.py` endpoint: GET /api/tick

................................................................................

Dependency:

	pip install pandas==2.2.2

................................................................................

Functionality:

	Loads raw ByBit tick-level trade CSV into a cleaned and aggregated
	DataFrame. Timestamps are converted to seconds with millisecond
	precision. Per timestamp, buy/sell actions are grouped separately,
	aggregated, and net volume/side/price is computed based on dominance.

................................................................................

IO Structure:

	Input:
		CSV with columns: ['timestamp', 'price', 'side', 'volume']
	Output:
		pd.DataFrame with:
			- 'time'   : float (UNIX timestamp in seconds, ms-preserved)
			- 'value'  : float (price from dominant side)
			- 'side'   : str ('buy' or 'sell')
			- 'volume' : float (net volume = buy - sell)

	NOTE:
		- Raw timestamps in milliseconds are converted to seconds.
		- Duplicate timestamps are aggregated by side, and net dominance
		  determines both volume and price.
		- No timezone or local-time conversion is done here; this is
		  handled entirely by the frontend.

................................................................................"""

import pandas as pd


def load_trades(path: str) -> pd.DataFrame:
	"""
	Load and aggregate ByBit trade CSV into sorted DataFrame by dominant side.

	Returns:
		pd.DataFrame with columns: ['time', 'value', 'side', 'volume']
		- time   : float (UNIX timestamp in seconds, with ms precision)
		- value  : price (from dominant side)
		- side   : 'buy' or 'sell' (net directional flow)
		- volume : net volume (buy - sell), aggregated per ms timestamp
	"""
	# Read raw CSV into DataFrame
	df = pd.read_csv(path)

	# Drop 'rpi' column if present (some ByBit formats include it)
	df = df.drop(columns=["rpi"], errors="ignore")

	# Rename columns for internal clarity
	df = df.rename(columns={
		"timestamp": "time",
		"price"    : "value"
	})[["time", "value", "side", "volume"]]

	# ⚠️ Convert time from milliseconds to seconds (float)
	# This preserves ms-precision as required by Lightweight Charts
	df["time"] = df["time"] / 1000

	# --- Begin Aggregation Per Timestamp ---

	# Group by (time, side) to prepare for directional net volume calc
	grouped = (
		df.groupby(["time", "side"])
		.agg(
			# Volume-weighted average price
			value=(
				"value",
				lambda x: (
					(x * df.loc[x.index, "volume"]).sum() /
					df.loc[x.index, "volume"].sum()
				)
			),
			# Total volume per direction
			volume=("volume", "sum")
		)
		.reset_index()
	)

	# Pivot side-wise structure into flat columns
	pivoted = grouped.pivot(
		index="time",
		columns="side",
		values=["value", "volume"]
	)
	pivoted.columns = ["_".join(col) for col in pivoted.columns]
	pivoted = pivoted.fillna(0)

	# Compute net directional flow (buy - sell)
	pivoted["net_volume"] = (
		pivoted.get("volume_buy", 0) - pivoted.get("volume_sell", 0)
	)

	# Decide dominant side by net flow direction
	pivoted["side"] = pivoted["net_volume"].apply(
		lambda x: "buy" if x > 0 else "sell"
	)

	# Pick price from dominant side
	def pick_price(row):
		return (
			row["value_buy"] if row["net_volume"] > 0 else row["value_sell"]
		)

	pivoted["value"] = pivoted.apply(pick_price, axis=1)

	# Final DataFrame structure: [time, value, side, volume]
	result = pivoted[["value", "side", "net_volume"]].reset_index()
	result = result.rename(columns={"net_volume": "volume"})

	# Sort chronologically
	result = result.sort_values("time").reset_index(drop=True)

	return result
