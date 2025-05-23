r"""................................................................................

How to Use:

	Called internally via `app.py` endpoints:
		- GET /api/tick
		- GET /api/orderbook

................................................................................

Dependency:

	pip install pandas==2.2.2

................................................................................

Functionality:

	Provides:
		- load_trades(): preprocesses execution (CSV) data
		- load_orderbook(): parses NDJSON order book data
		- align_orderbook_to_ticks(): matches DOM state to each tick

	Timestamp alignment: each tick is assigned the closest
	≤ ts order book snapshot, or "N/A" if none exists.

................................................................................

IO Structure:

	Input:
		- CSV file: ['timestamp', 'price', 'side', 'volume']
		- .data file: NDJSON with {'type', 'ts', 'data': {'a': [], 'b': []}}

	Output:
		- load_trades(): pd.DataFrame with [time, value, side, volume]
		- load_orderbook(): dict[ts: float] → snapshot
		- align_orderbook_to_ticks(): dict[tick_ts: float] → DOM

................................................................................

TODO (DO NOT DELETE, ChatGPT):

    The aggregation logic in the load_trades() method requires
    refinement—particularly in how the following fields are aggregated
    for ticks sharing the same UNIX timestamp:
        - time,
        - price (originally, value),
        - volume, and
        - side.
        
    For example, negative `volume` caused by stronger sell pressure
    can be misleading. Moreover, when multiple executions occur within
    the same UNIX timestamp, there must be a clear and consistent rule
    for selecting the representative `price`.

................................................................................"""

import pandas as pd
import json
import bisect


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

def load_orderbook(path: str) -> dict:
	"""
	Load ByBit DOM NDJSON and reconstruct time-indexed snapshots.

	Returns:
		dict[ts: float] → {"a": [...], "b": [...]}
	"""
	dom_dict = {}
	current  = {"a": [], "b": []}

	with open(path, "r") as f:
		for line in f:
			entry = json.loads(line)

			ts    = entry.get("ts") / 1000  # convert ms to float seconds
			etype = entry.get("type")
			data  = entry.get("data", {})

			if etype == "snapshot":
				current = {
					"a": data.get("a", []),
					"b": data.get("b", [])
				}
			elif etype == "delta":
				for side in ("a", "b"):
					levels = {price: size for price, size in current[side]}
					for price, size in data.get(side, []):
						if float(size) == 0:
							levels.pop(price, None)
						else:
							levels[price] = size
					current[side] = sorted(
						[(p, s) for p, s in levels.items()],
						key=lambda x: float(x[0]),
						reverse=(side == "b")
					)

			dom_dict[ts] = {
				"a": current["a"].copy(),
				"b": current["b"].copy()
			}

	return dom_dict


def align_orderbook_to_ticks(
	tick_df: pd.DataFrame,
	ob_dict: dict[float, dict]
) -> dict:
	"""
	Map each tick timestamp to the closest past DOM snapshot (≤ ts).

	Returns:
		dict[tick_ts] → DOM snapshot or "N/A"
	"""
	snap_times = sorted(ob_dict.keys())  # ascending float timestamps
	snap_map   = {}

	for tick_ts in tick_df["time"]:
		idx = bisect.bisect_right(snap_times, tick_ts)

		if idx == 0:
			snap_map[tick_ts] = "N/A"
		else:
			nearest_ts = snap_times[idx - 1]
			snap_map[tick_ts] = ob_dict[nearest_ts]

	return snap_map
