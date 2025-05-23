r"""...............................................................................
MODULE OVERVIEW:

	This module handles low-level ingestion and preprocessing of ByBit market data
	for use in both real-time visualization (main.ts) and downstream reinforcement
	learning pipelines.

	It serves as the true backend for data-centric signal development, decoupling
	raw formats from frontend rendering and RL agent input.

...............................................................................
ARCHITECTURE:

	↪ loader.py (this file)
		- load_trades(): parses and aggregates ByBit execution CSV
		- load_orderbook(): reconstructs DOM snapshots from NDJSON
		- align_orderbook_to_ticks(): matches DOM state to each tick

	↪ app.py
		- Invokes this module at server startup to preload data
		- Exposes API endpoints used by frontend (e.g., /api/tick)

	↪ main.ts (frontend)
		- Renders:
			• Tick series as price chart (left)
			• DOM overlays using canvas (right)

...............................................................................
DEPENDENCIES:

	• pandas  (2.2.2)
	• json    (Python 3.9.19 standard library)
	• bisect  (Python 3.9.19 standard library)

...............................................................................
DATA FLOW & FUNCTIONALITY:

	Input files (symbol="UNIUSDC", date="2025-05-17"):

		• data/UNIUSDC_2025-05-17.csv
		    → Raw trade history (ByBit Spot Execution)
		
		• data/2025-05-17_UNIUSDC_ob200.data
		    → NDJSON-formatted tick-level order book deltas and snapshots

	Provided functions:

		• load_trades():
		    - Aggregates price/volume per millisecond
		    - Extracts VWAP from dominant flow direction (buy/sell)
		    - Output: pd.DataFrame [time, value, side, volume]

		• load_orderbook():
		    - Applies DOM deltas to reconstruct book state at each tick
		    - Output: dict[timestamp] → snapshot {"a": [...], "b": [...]}

		• align_orderbook_to_ticks():
		    - Finds latest DOM snapshot prior to each tick (≤ ts)
		    - Output: dict[tick_ts] → matching DOM (or "N/A")

...............................................................................
ROLE IN RL PIPELINE:

	• This loader module provides a unified data format that serves both
	  frontend visualization and RL agent training — maintaining consistency
	  between what is visualized and what is used for decision making.

	• The aggregation logic in `load_trades()` supports:
	    - Directional signal extraction via signed net volume
	    - Flexible time-binning (currently: millisecond resolution)
	    - VWAP (Volume-Weighted Average Price) computation to ensure
	      representative pricing under dense multi-trade scenarios

	• Future refinements may include:
	    - Custom time intervals (e.g., 50ms buckets)
	    - Configurable definitions for "dominant flow" or "execution strength"
	    - Agent-defined dynamic state transformation

...............................................................................
📚 DATA FORMAT REFERENCE:

	- 📘 OrderBook Format (bybit_orderbook_format.md)
	    → Tick-level DOM snapshots and deltas (.data)

	- 📙 Execution Format (bybit_execution_format.md)
	    → Trade history with RPI flags (.csv)

	- 🔗 ByBit Official Explanation:
	    https://bybit-exchange.github.io/docs/tax/explain

...............................................................................
FUTURE NOTE (DO NOT DELETE, ChatGPT):

	The current aggregation and alignment logic is consistent and reliable,
	but subject to refinement as the agent’s state representation evolves.

..............................................................................."""


import pandas as pd    # Primary tabular data structure for processing tick stream
import json            # (Used in other parts) for NDJSON parsing of DOM snapshots
import bisect          # Used for binary search matching during time alignment

def load_trades(path: str) -> pd.DataFrame:
	"""
	Load and aggregate ByBit trade CSV into sorted DataFrame by dominant side.

	Returns:
		pd.DataFrame with columns: ['time', 'value', 'side', 'volume']
		- time   : float (UNIX timestamp in seconds, with ms precision)
		- value  : price (from dominant side)
		- side   : 'buy' or 'sell' (net directional flow)
		- volume : net volume (buy - sell), aggregated per ms timestamp

	Used by both:
		↪ RL signal preprocessing
		↪ app.py for serving to frontend (left chart)
	"""
	
	# -------------------------------------------------------------------------
	# Step 1: Read raw tick data from CSV
	# Raw columns include: timestamp (ms), price, side, volume, (optionally) rpi
	# -------------------------------------------------------------------------
	df = pd.read_csv(path)

	# Some ByBit CSVs include 'rpi' (Relative Price Indicator) — drop if exists
	df = df.drop(columns=["rpi"], errors="ignore")

	# Rename columns to internal convention: 'time', 'value', 'side', 'volume'
	df = df.rename(columns={
		"timestamp": "time",
		"price"    : "value"
	})[["time", "value", "side", "volume"]]

	# ⚠️ Convert time from ms → sec (float)
	# Required for compatibility with frontend charting (Lightweight Charts)
	df["time"] = df["time"] / 1000

	# -------------------------------------------------------------------------
	# Step 2: Aggregate by (time, side)
	#
	# - ByBit execution traces may contain multiple ticks per ms (same time).
	# - Here, we aggregate each (time, side) pair to calculate:
	#   • Directional volume
	#   • Volume-weighted average price (VWAP)
	# -------------------------------------------------------------------------
	grouped = (
		df.groupby(["time", "side"])
		.agg(
			value=(
				"value",
				# VWAP: Σ(price × vol) / Σ(vol)
				lambda x: (
					(x * df.loc[x.index, "volume"]).sum() /
					df.loc[x.index, "volume"].sum()
				)
			),
			volume=("volume", "sum")  # Total directional volume
		)
		.reset_index()
	)

	# -------------------------------------------------------------------------
	# Step 3: Pivot side-wise structure for net flow calculation
	# After pivot: each time has:
	#   • volume_buy, volume_sell
	#   • value_buy,  value_sell
	# NaN is replaced with 0 (e.g., no 'sell' trades at a time)
	# -------------------------------------------------------------------------
	pivoted = grouped.pivot(
		index="time",
		columns="side",
		values=["value", "volume"]
	)
	pivoted.columns = ["_".join(col) for col in pivoted.columns]
	pivoted = pivoted.fillna(0)

	# -------------------------------------------------------------------------
	# Step 4: Compute net flow and label directional side
	#
	# RL or visual signal may benefit from net directional pressure.
	# This net volume is (buy - sell), not abs(buy) + abs(sell).
	# If net > 0 → buy side dominates (green bar)
	# If net < 0 → sell side dominates (red bar)
	# -------------------------------------------------------------------------
	pivoted["net_volume"] = (
		pivoted.get("volume_buy", 0) - pivoted.get("volume_sell", 0)
	)

	# Apply label for dominant side
	pivoted["side"] = pivoted["net_volume"].apply(
		lambda x: "buy" if x > 0 else "sell"
	)

	# -------------------------------------------------------------------------
	# Step 5: Assign a price to each time tick using dominant side VWAP
	#
	# Note: 'value_buy' and 'value_sell' are only meaningful if volume exists.
	# We use the price from the side with net volume dominance.
	# -------------------------------------------------------------------------
	def pick_price(row):
		return (
			row["value_buy"] if row["net_volume"] > 0 else row["value_sell"]
		)

	pivoted["value"] = pivoted.apply(pick_price, axis=1)

	# -------------------------------------------------------------------------
	# Step 6: Final formatting for downstream use
	#
	# Output fields:
	#   - time   (float, seconds)
	#   - value  (VWAP from dominant side)
	#   - side   ('buy' or 'sell')
	#   - volume (net signed volume)
	#
	# ⚠️ This format is directly served by app.py → frontend (main.ts)
	#     where it's plotted in the left chart and used for tooltips.
	# -------------------------------------------------------------------------
	result = pivoted[["value", "side", "net_volume"]].reset_index()
	result = result.rename(columns={"net_volume": "volume"})

	# Enforce chronological order
	result = result.sort_values("time").reset_index(drop=True)

	return result

def load_orderbook(path: str) -> dict:
	"""
	Load ByBit DOM NDJSON and reconstruct time-indexed snapshots.

	Returns:
		dict[ts: float] → {"a": [...], "b": [...]}

	Format:
		- "a" → ask side (ascending by price)
		- "b" → bid side (descending by price)

	Used by:
		↪ align_orderbook_to_ticks() → app.py
		↪ GUI canvas renderer in main.ts (via DOM fetch)
	"""

	# -------------------------------------------------------------------------
	# Initialize:
	# dom_dict: { timestamp → snapshot dict {a: [...], b: [...]} }
	# current : working orderbook state to accumulate deltas
	# -------------------------------------------------------------------------
	dom_dict = {}
	current  = {"a": [], "b": []}

	# NDJSON format: each line is a JSON object representing either
	# a full "snapshot" or a partial "delta" of the orderbook
	with open(path, "r") as f:
		for line in f:
			entry = json.loads(line)

			# Timestamp: originally in ms → convert to float seconds
			ts    = entry.get("ts") / 1000
			etype = entry.get("type")
			data  = entry.get("data", {})

			# -----------------------------------------------------------------
			# If this line is a full snapshot:
			# Reset the current working orderbook to this clean state.
			# -----------------------------------------------------------------
			if etype == "snapshot":
				current = {
					"a": data.get("a", []),
					"b": data.get("b", [])
				}

			# -----------------------------------------------------------------
			# If this line is a delta:
			# - Apply add/update/remove on top of `current`
			# - Any price with size=0 is deleted
			# - Result is sorted for each side:
			#     • asks  ("a") → ascending
			#     • bids  ("b") → descending
			# -----------------------------------------------------------------
			elif etype == "delta":
				for side in ("a", "b"):
					# Create a price→size map from current state
					levels = {price: size for price, size in current[side]}

					for price, size in data.get(side, []):
						if float(size) == 0:
							# Remove this level if size is zero (cancel)
							levels.pop(price, None)
						else:
							# Insert or update this level
							levels[price] = size

					# Sort price levels:
					#   - ascending for ask ("a")
					#   - descending for bid ("b")
					current[side] = sorted(
						[(p, s) for p, s in levels.items()],
						key=lambda x: float(x[0]),
						reverse=(side == "b")
					)

			# -----------------------------------------------------------------
			# Save current snapshot under current timestamp
			# Important: must deep-copy because current is mutable
			# -----------------------------------------------------------------
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

	Used by:
		↪ app.py → GET /api/orderbook
		↪ main.ts → hover handler for DOM canvas rendering
	"""

	# -------------------------------------------------------------------------
	# Preprocess:
	# Extract and sort all available DOM timestamps in ascending order
	# This allows binary search via `bisect_right()`
	# -------------------------------------------------------------------------
	snap_times = sorted(ob_dict.keys())  # e.g., [0.123, 0.140, 0.189, ...]

	# Output map: tick_ts (float) → DOM snapshot (dict) or "N/A"
	snap_map = {}

	# -------------------------------------------------------------------------
	# For each tick timestamp:
	# - Find the nearest DOM snapshot timestamp `t_snap` such that
	#       t_snap ≤ tick_ts
	# - If no such snapshot exists, return "N/A"
	#
	# This mapping logic assumes that DOM snapshots were sorted by time
	# and stored densely enough to allow alignment. If tick data comes
	# before the first DOM, the value is "N/A".
	# -------------------------------------------------------------------------
	for tick_ts in tick_df["time"]:
		# bisect_right returns index where tick_ts could be inserted
		# to preserve sort order: we want the value just before it
		idx = bisect.bisect_right(snap_times, tick_ts)

		if idx == 0:
			# No snapshot exists before this tick timestamp
			snap_map[tick_ts] = "N/A"
		else:
			# Take the most recent snapshot at or before tick_ts
			nearest_ts = snap_times[idx - 1]
			snap_map[tick_ts] = ob_dict[nearest_ts]

	return snap_map