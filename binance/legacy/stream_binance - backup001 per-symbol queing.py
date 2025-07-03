# stream_binance.py

r"""................................................................................

How to Use:

	🧪 Development Mode (e.g., Windows, debugging):
	$ python stream_binance.py

	🐧 Production Mode (Ubuntu, self-contained executable):
	$ ./stream_binance

Note:
	- The production binary is built via `compile_linux.bat`, which uses Docker
	  to produce a statically linked Linux executable from `stream_binance.py`.
	- No Python environment is required at runtime for the production build.

Temporary Simple Order Book Rendering:
		http://localhost:8000/orderbook/btcusdc

................................................................................

Dependency:
	Python ≥ 3.9
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	jinja2==3.1.3

Functionality:
	Stream Binance depth20 order books (100ms interval) via combined websocket.
	Maintain top-20 in-memory symbol_snapshots_to_render for each symbol.
	Periodically persist symbol_snapshots_to_render to JSONL → zip → aggregate daily.
	Serve REST endpoints for JSON/HTML access and health monitoring.

IO Structure:
	Config:
		- get_binance_chart.conf
			• Shared between `stream_binance.py` and `get_binance_chart.py`
			• Defines symbols, backoff intervals, output paths, etc.
	Inputs:
		- Binance websocket:
		  wss://stream.binance.com:9443/stream?streams={symbol}@depth20@100ms
	Outputs:
		- Zipped JSONL files (per-symbol, per-minute/day):
		  ./data/binance/orderbook/temporary/{symbol}_orderbook_{YYYY-MM-DD}/
		- Daily merged archive:
		  ./data/binance/orderbook/{symbol}_orderbook_{YYYY-MM-DD}.zip
		- API Endpoints:
			/health/live		→ liveness probe
			/health/ready		→ readiness after first snapshot
			/state/{symbol}		→ JSON: current top-20 snapshot
			/orderbook/{symbol}	→ HTML: real-time bid/ask viewer
			
................................................................................

Binance Official GitHub Manual:
	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

................................................................................
"""

# ─────────────────────────────────────────────────────────────
# 📦 Built-in Standard Library Imports (Grouped by Purpose)
# ─────────────────────────────────────────────────────────────

import asyncio, threading, time, random		# Async & Scheduling
import sys, os, shutil, zipfile				# File I/O & Path
import json, statistics						# Data Processing
from collections import deque

# ───────────────────────────────────────────────────────────────────────────────
# 📝 Logging Configuration: Rotating log file + console output with UTC timestamps
# ───────────────────────────────────────────────────────────────────────────────

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────
# 👤 Custom Formatter: Ensures all log timestamps are in UTC
# ─────────────────────────────────────────────────────────────

class UTCFormatter(logging.Formatter):

	"""
	Custom log formatter that converts log record timestamps
	to ISO 8601 UTC format (e.g., 2025-07-03T14:23:01.123456+00:00).
	"""

	def formatTime(self, record, datefmt=None):
		# Convert record creation time to UTC datetime
		dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
		
		# Return formatted string based on optional format string
		if datefmt:
			return dt.strftime(datefmt)
		
		# Default to ISO 8601 format
		return dt.isoformat()

# ─────────────────────────────────────────────────────────────
# ⚙️ Formatter Definition (applied to both file and console)
# ─────────────────────────────────────────────────────────────

log_formatter = UTCFormatter("[%(asctime)s] %(levelname)s: %(message)s")

# ─────────────────────────────────────────────────────────────
# 💾 Rotating File Handler Configuration
# - Log file: stream_binance.log
# - Rotation: 10 MB per file
# - Retention: up to 3 old versions (e.g., .1, .2, .3)
# ─────────────────────────────────────────────────────────────

file_handler = RotatingFileHandler(
	"stream_binance.log",
	maxBytes=10_000_000,       # Rotate after 10 MB
	backupCount=3              # Keep 3 backups
)
file_handler.setFormatter(log_formatter)

# ─────────────────────────────────────────────────────────────
# 📺 Console Handler Configuration
# - Mirrors the same UTC timestamp format
# ─────────────────────────────────────────────────────────────

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# ─────────────────────────────────────────────────────────────
# 🧠 Logger Setup
# - Reuses "uvicorn.error" logger to integrate with FastAPI stack
# - Logging level: INFO
# - Prevents propagation to ancestor loggers to avoid duplication
# ─────────────────────────────────────────────────────────────

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
logger.propagate = False  # Avoid double logging

# Attach both file and console handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ─────────────────────────────────────────────────────────────
# 📦 Third-Party Dependencies (from requirements.txt)
# ─────────────────────────────────────────────────────────────

# 📡 CORE ──────────────────────────────────────────────────────
# websockets:
#   - Core dependency for Binance L2 stream (`depth20@100ms`)
#   - Absolutely required for order book ingestion

import websockets

# 🌐 FastAPI Runtime Backbone ──────────────────────────────────────────────
# FastAPI:
#   - Lightweight ASGI framework used as core runtime environment
#   - Powers both REST API endpoints and underlying logging system via `uvicorn`
#   - Enables HTTP access for:
#       • /state/{symbol}        → latest order book snapshot (JSON)
#       • /orderbook/{symbol}    → real-time bid/ask viewer (HTML)
#       • /health/live, /ready   → liveness & readiness probes
#   - Logging is routed via `uvicorn.error`, so FastAPI is integral even
#     when HTML rendering is not used.
# ⚠️ Removal of FastAPI implies rewriting logging + API infrastructure
# jinja2 (via FastAPI templates):
#   - Optional HTML rendering for order book visualization

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ─────────────────────────────────────────────────────────────
# 📁 Utility: PyInstaller-Compatible Resource Resolver
# ─────────────────────────────────────────────────────────────
def resource_path(relative_path: str) -> str:

	"""
	Resolve an absolute filesystem path to bundled resource files
	(e.g., templates, config files), ensuring compatibility with both:

	  • 🧪 Development mode  — source-level execution on Windows
	  • 🐧 Deployment mode   — PyInstaller-frozen binary on Ubuntu Linux

	⚠️ WARNING:
	This project is built and distributed as a self-contained Linux binary
	using PyInstaller inside a Docker container (see Dockerfile).
	At runtime, all bundled files are extracted to a temporary directory,
	typically located at `/tmp/_MEIxxxx`, and made available via `sys._MEIPASS`.

	To support both dev and production execution seamlessly, this function
	resolves the correct base path at runtime.

	Args:
		relative_path (str):
			Path relative to this script — e.g.,
			  • "templates/"                   → for HTML rendering
			  • "get_binance_chart.conf"       → chart API config

	Returns:
		str:
			Absolute path to the resource file, portable across environments.
	"""

	base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
	return os.path.join(base, relative_path)

# ─────────────────────────────────────────────────────────────
# ⚙️ FastAPI Initialization + HTML Template Binding
# ─────────────────────────────────────────────────────────────
# FastAPI serves as the **core runtime backbone** for this application.
# It is not merely optional; several key subsystems depend on it:
#
#   1. 📊 Logging Integration:
#      - Logging is routed via `uvicorn.error`, which is managed by FastAPI's ASGI server.
#      - This means our logger (`logger = logging.getLogger("uvicorn.error")`) is **active**
#        and functional even before we explicitly launch the app, as long as FastAPI is imported.
#
#   2. 🌐 REST API Endpoints:
#      - Used for health checks, JSON-based order book access, and real-time UI rendering.
#
#   3. 🧱 HTML UI Layer (Optional but Useful):
#      - The Jinja2 template system is integrated via FastAPI to serve HTML at `/orderbook/{symbol}`.
#
# ⚠️ If FastAPI were removed, the following features would break:
#     → Logging infrastructure
#     → REST endpoints (/health, /state)
#     → HTML visualization
#
# So although not all FastAPI features are always used, **its presence is structurally required**.

app = FastAPI()

# Bind template directory (used for rendering HTML order book UI)
# `resource_path()` ensures compatibility with PyInstaller-frozen Linux binaries.

templates = Jinja2Templates(directory=resource_path("templates"))

# ───────────────────────────────
# ⚙️ Configuration Loader (.conf)
# ───────────────────────────────
# Shared configuration file used by both `stream_binance.py` and
# `get_binance_chart.py`, defining key runtime parameters such as:
#
#   • SYMBOLS              → Binance symbols to stream (e.g., BTCUSDT)
#   • SAVE_INTERVAL_MIN    → File rotation interval for snapshot persistence
#   • LOB_DIR              → Output directory for JSONL and ZIP files
#   • BASE_BACKOFF, etc.   → Retry strategy for websocket reconnects
#
# 📄 Filename: get_binance_chart.conf
# Format: Plaintext `KEY=VALUE`, supporting inline `#` comments.
#
# ⚠️ IMPORTANT:
# This file is loaded using `resource_path()` to ensure correct resolution
# under both dev (Windows) and production (PyInstaller/Linux) modes.
# When bundled with PyInstaller, the config is packaged and extracted to a
# temp folder at runtime (`/tmp/_MEIxxxx`), resolved via `sys._MEIPASS`.

CONFIG_PATH = "get_binance_chart.conf"
CONFIG = {}  # Global key-value store loaded during import

def load_config(conf_path: str):

	"""
	Load a plain `.conf` file with `KEY=VALUE` pairs.
	Ignores blank lines and lines starting with `#`.
	Also strips inline comments after `#`.

	Populates the global CONFIG dictionary.

	Args:
		conf_path (str): Relative path to the configuration file,
						 resolved via `resource_path()` if necessary.

	Example:
		get_binance_chart.conf:
			SYMBOLS = BTCUSDT,ETHUSDT  # Comma-separated symbols
			SAVE_INTERVAL_MIN = 1
			LOB_DIR = ./data/binance/orderbook/
	"""

	try:
		with open(conf_path, 'r', encoding='utf-8') as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				line = line.split("#", 1)[0].strip()
				if "=" in line:
					key, val = line.split("=", 1)
					CONFIG[key.strip()] = val.strip()
	except Exception as e:
		logger.error(f"Failed to load config from {conf_path}: {e}")

# 🔧 Load config via resource_path() for PyInstaller compatibility

load_config(resource_path(CONFIG_PATH))

# ─────────────────────────────────────────────────────────────
# 📊 Stream Parameters Derived from Config
# ─────────────────────────────────────────────────────────────
# Parse symbol and latency settings from .conf, and derive:
#   • `WS_URL` for combined Binance L2 depth20@100ms stream
#   • Tracking dicts for latency and update consistency

SYMBOLS = [s.lower() for s in CONFIG.get("SYMBOLS", "").split(",") if s.strip()]
if not SYMBOLS:
	raise RuntimeError("No SYMBOLS loaded from config.")

STREAMS_PARAM	= "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL			= f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

# ─────────────────────────────────────────────────────────────
# 📈 Latency Measurement Parameters
# These control how latency is estimated from the @depth stream:
#   - LATENCY_DEQUE_SIZE: buffer size for per-symbol latency samples
#   - LATENCY_SAMPLE_MIN: number of samples required before validation
#   - LATENCY_THRESHOLD_SEC: max latency allowed for stream readiness
# ─────────────────────────────────────────────────────────────

LATENCY_DEQUE_SIZE    = int(CONFIG.get("LATENCY_DEQUE_SIZE", 10))
LATENCY_SAMPLE_MIN    = int(CONFIG.get("LATENCY_SAMPLE_MIN", 10))
LATENCY_THRESHOLD_SEC = float(CONFIG.get("LATENCY_THRESHOLD_SEC", 0.5))
LATENCY_SIGNAL_SLEEP  = float(CONFIG.get("LATENCY_SIGNAL_SLEEP", 0.2))

# ─────────────────────────────────────────────────────────────
# 🧠 Runtime Per-Symbol State
# These dicts track stream validity:
#   - median_latency_dict: rolling latency cache (in seconds)
#   - depth_update_id_dict: last seen update ID (to deduplicate)
# ─────────────────────────────────────────────────────────────

median_latency_dict   = {symbol: 0.0 for symbol in SYMBOLS}
depth_update_id_dict  = {symbol:   0 for symbol in SYMBOLS}

# ─────────────────────────────────────────────────────────────
# 🕒 Backoff Strategy & Snapshot Save Policy
# Configures:
#   • WebSocket reconnect behavior (exponential backoff)
#   • Order book snapshot directory and save intervals
#   • Optional data purging upon date rollover
# ─────────────────────────────────────────────────────────────

BASE_BACKOFF         = int(CONFIG.get("BASE_BACKOFF", 2))
MAX_BACKOFF          = int(CONFIG.get("MAX_BACKOFF", 30))
RESET_CYCLE_AFTER    = int(CONFIG.get("RESET_CYCLE_AFTER", 7))
RESET_BACKOFF_LEVEL	 = int(CONFIG.get("RESET_BACKOFF_LEVEL", 3))

LOB_DIR = CONFIG.get("LOB_DIR", "./data/binance/orderbook/")

PURGE_ON_DATE_CHANGE = int(CONFIG.get("PURGE_ON_DATE_CHANGE", 1))
SAVE_INTERVAL_MIN    = int(CONFIG.get("SAVE_INTERVAL_MIN", 1440))

if SAVE_INTERVAL_MIN > 1440:
	raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

# 📁 Ensure order book directory exists

os.makedirs(LOB_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 📦 Runtime Memory Buffers & Async File Handles
#
# Maintains:
#
#   • symbol_snapshots_to_render
# 	  → In-memory L2 order book snapshot per symbol
#
#   • file_handles
# 	  → Active async file writers per symbol
# ─────────────────────────────────────────────────────────────

symbol_snapshots_to_render:	  dict[str, dict] = {}
file_handles: dict[str, tuple[str, asyncio.StreamWriter]] = {}

# ─────────────────────────────────────────────────────────────
# 📦 File Utilities: Naming, Compression, and Intraday Merging
# ─────────────────────────────────────────────────────────────

def get_file_suffix(interval_min: int, event_ts_ms: int) -> str:

	"""
	Returns a timestamp-based suffix for snapshot filenames.

	Uses `event_ts_ms` from the snapshot's 'eventTime' field, which reflects
	the client-side receipt time of the Binance WebSocket message.

	Args:
		interval_min (int): Save interval in minutes.
		event_ts_ms (int): Client-received timestamp (ms) from snapshot.

	Returns:
		str: e.g., '2025-07-01_13-00' or '2025-07-01' if daily.
	"""

	ts = datetime.utcfromtimestamp(event_ts_ms / 1000)

	if interval_min >= 1440:	return ts.strftime("%Y-%m-%d")
	else:						return ts.strftime("%Y-%m-%d_%H-%M")

# .............................................................

def get_date_from_suffix(suffix: str) -> str:

	"""
	Extracts the date portion from a file suffix.

	Args:
		suffix (str): Filename suffix such as '2025-06-27_13-15'

	Returns:
		str: Date string in 'YYYY-MM-DD'
	"""

	return suffix.split("_")[0]

# .............................................................

def zip_and_remove(src_path: str):

	"""
	Zips the specified .jsonl file and removes the original.

	Args:
		src_path (str): Path to the JSONL file to compress
	"""

	if os.path.exists(src_path):
		zip_path = src_path.replace(".jsonl", ".zip")
		with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.write(src_path, arcname=os.path.basename(src_path))
		os.remove(src_path)

# .............................................................

def merge_day_zips_to_single_jsonl(
	symbol: str,
	day_str: str,
	base_dir: str,
	purge: bool = True
):

	"""
	Merge all per-minute zipped order book symbol_snapshots_to_render into a single .jsonl file for the given day,
	then re-compress the result as a single zip archive. Optionally purge temporary files.

	This routine is robust against missing files and concurrent I/O artifacts,
	and is designed for post-processing in long-running systems where partial writes may occur.

	Args:
		symbol (str):
			Trading symbol, e.g., "btcusdt"
		day_str (str):
			Target date in "YYYY-MM-DD" format
		base_dir (str):
			Root path where order book data is stored
		purge (bool):
			If True, deletes the per-minute zipped snapshot folder after merging

	Handled Scenarios:
		- Temporary folder may not exist (e.g., stream failure or date mismatch)
		- Folder may exist but be empty (e.g., early startup with no symbol_snapshots_to_render)
		- Individual .zip files might be missing or removed mid-process
		- Corrupted zips or concurrent file deletions are caught and logged safely
	"""

	# ── Construct working directories and target paths
	tmp_dir = os.path.join(
		base_dir,
		"temporary",
		f"{symbol.upper()}_orderbook_{day_str}"
	)
	merged_path = os.path.join(
		base_dir,
		f"{symbol.upper()}_orderbook_{day_str}.jsonl"
	)

	# ── 1. Abort early if directory is missing (no data captured for this day)
	if not os.path.isdir(tmp_dir):
		return

	# ── 2. List all zipped minute-level symbol_snapshots_to_render (may be empty)
	zip_files = [f for f in os.listdir(tmp_dir) if f.endswith(".zip")]
	if not zip_files:
		return

	try:
		# ── 3. Open output file for merged .jsonl content
		with open(merged_path, "w", encoding="utf-8") as fout:
			# ── 4. Process each zip file in chronological order
			for zip_file in sorted(zip_files):
				zip_path = os.path.join(tmp_dir, zip_file)

				# ── 5. Unzip each file and stream its lines directly into the merged file
				with zipfile.ZipFile(zip_path, "r") as zf:
					for member in zf.namelist():
						with zf.open(member) as f:
							for raw in f:
								fout.write(raw.decode("utf-8"))

		# ── 6. Recompress the consolidated .jsonl into a final single-archive zip
		final_zip = merged_path.replace(".jsonl", ".zip")
		with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.write(merged_path, arcname=os.path.basename(merged_path))

		# ── 7. Remove intermediate plain-text .jsonl file after compression
		if os.path.exists(merged_path):
			os.remove(merged_path)

		# ── 8. Optionally delete the original temp folder containing per-minute zips
		if purge:
			shutil.rmtree(tmp_dir)

	except FileNotFoundError as e:
		# ── Likely due to concurrent cleanup (e.g., temp folder or zip deleted externally)
		logger.warning(
			f"[merge_day_zips] No files found to merge for {symbol} on {day_str}: {e}"
		)
		return

	except Exception as e:
		# ── Catch-all safeguard for any other unexpected I/O error
		logger.error(
			f"[merge_day_zips] Unexpected error merging {symbol} on {day_str}: {e}",
			exc_info=True
		)
		return

# .............................................................

def merge_all_symbols_for_day(symbols: list[str], day_str: str):

	"""
	Batch merge: For each symbol, invoke merging logic for zipped intraday symbol_snapshots_to_render.

	Args:
		symbols (list[str]): List of trading symbols (lowercase)
		day_str (str): Target day (YYYY-MM-DD) to consolidate

	Notes:
		- purge flag is toggled globally via PURGE_ON_DATE_CHANGE setting (0 or 1)
		- Merges are independent across symbols
	"""

	for symbol in symbols:
		merge_day_zips_to_single_jsonl(
			symbol,
			day_str,
			LOB_DIR,
			purge=(PURGE_ON_DATE_CHANGE == 1)
		)

# ─────────────────────────────────────────────────────────────
# 🕓 Latency Control: Measurement, Thresholding, and Flow Gate
# ─────────────────────────────────────────────────────────────

async def gate_streaming_by_latency() -> None:

	"""
	🔁 Streaming Controller based on Latency

	This coroutine manages the `event_stream_enable` flag,
	which controls whether the main order book stream (`put_snapshot`) 
	is permitted to run.

	It does so by observing `event_latency_valid`, a signal set by the 
	latency estimation loop (`estimate_latency_via_diff_depth`) only when:
		- Every tracked symbol has at least LATENCY_SAMPLE_MIN samples, and
		- Their median latency is below LATENCY_THRESHOLD_SEC.

	Behavior:

	- Initial Warm-up Phase:
		• If no symbols have latency samples yet, logs a one-time warm-up message.
	- Latency OK → Allow Streaming:
		• If `event_latency_valid` is set, enables `event_stream_enable`.
		• This unblocks `await event_stream_enable.wait()` in `put_snapshot()`.
	- Latency NOT OK → Pause Streaming:
		• If `event_latency_valid` becomes unset, disables `event_stream_enable`,
		  but only if all symbols have some latency samples (i.e., warm-up is over).
		• This prevents premature pausing before data collection begins.

	Loop Interval:
		Controlled by `LATENCY_SIGNAL_SLEEP` (from config), e.g., 0.2 seconds.
	"""

	has_logged_warmup = False	# The initial launch of the program

	while True:

		latency_passed		= event_latency_valid.is_set()	# ⬅️ Acceptable latency verified
		stream_currently_on = event_stream_enable.is_set()	# ⬅️ Stream currently active

		has_any_latency = all(
			len(latency_dict[s]) > 0 for s in SYMBOLS
		)

		if latency_passed and not stream_currently_on:

			logger.info("Latency normalized. Enable order book stream.")
			event_stream_enable.set()
			has_logged_warmup = False

		elif not latency_passed:

			if not has_any_latency and not has_logged_warmup:

				logger.info("Warming up latency measurements...")
				has_logged_warmup = True

			elif has_any_latency and stream_currently_on:

				logger.warning("Latency degraded. Pausing order book stream.")
				event_stream_enable.clear()

		await asyncio.sleep(LATENCY_SIGNAL_SLEEP)

# .............................................................

async def estimate_latency_via_diff_depth() -> None:

	"""
	🔁 Latency Estimator via Binance @depth Stream

	This coroutine connects to the Binance `@depth` WebSocket stream 
	(not `@depth20@100ms`) to measure **effective downstream latency**
	for each tracked symbol.

	Latency is estimated by comparing:
		latency ≈ client_time_sec - server_time_sec

	Where:
	- `server_time_sec` is the server-side event timestamp (`E`).
	- `client_time_sec` is the actual receipt time on the local machine.
	This difference reflects:
		• Network propagation delay
		• OS-level socket queuing
		• Python event loop scheduling
	and thus represents a realistic approximation of **one-way latency**.

	Behavior:
	- Maintains a rolling deque of latency samples per symbol.
	- Once `LATENCY_SAMPLE_MIN` samples exist:
		• Computes median latency per symbol.
		• If all medians < `LATENCY_THRESHOLD_SEC`, sets `event_latency_valid`.
		• If excessive latency or disconnection, clears the signal.

	Purpose:
	- `event_latency_valid` acts as a global flow control flag.
	- Used by `gate_streaming_by_latency()` to pause/resume 
	order book streaming via `event_stream_enable`.

	Backoff:
	- On disconnection or failure, retries with exponential backoff and jitter.

	Notes:
	- This is **not** a true RTT (round-trip time) estimate.
	- But sufficient for gating real-time systems where latency 
	directly affects snapshot timestamp correctness.
	"""

	global median_latency_dict, depth_update_id_dict

	url = (
		"wss://stream.binance.com:9443/stream?"
		+ "streams=" + "/".join(f"{symbol}@depth" for symbol in SYMBOLS)
	)

	reconnect_attempt = 0

	while True:

		try:

			async with websockets.connect(url) as ws:

				logger.info(
					f"Connected to:\n"
					f"\t{url} (@depth)"
				)

				reconnect_attempt = 0  # Reset retry counter

				async for raw_msg in ws:
					
					message		= json.loads(raw_msg)
					data		= message.get("data", {})
					
					server_event_ts_ms = data.get("E")  # Server-side timestamp (in ms)

					if server_event_ts_ms is None:
						continue  # Drop malformed message

					stream_name	= message.get("stream", "")
					symbol		= stream_name.split("@", 1)[0].lower()

					if symbol not in SYMBOLS:
						continue  # Ignore unexpected symbols
					
					update_id	= data.get("u")

					if update_id is None or update_id <= depth_update_id_dict.get(symbol, 0):
						continue  # Duplicate or out-of-order update

					depth_update_id_dict[symbol] = update_id
					
					# ................................................................
					# Estimate latency (difference between client and server clocks)
					# ................................................................
					# `client_time_sec - server_time_sec` approximates one-way latency
					# (network + kernel + event loop) at the point of message receipt.
					# While not a true RTT, it reflects realistic downstream delay
					# and is sufficient for latency gating decisions in practice.
					# ................................................................

					server_time_sec = server_event_ts_ms / 1000.0
					client_time_sec = time.time()
					latency_sec = max(0.0, client_time_sec - server_time_sec)

					# ................................................................

					# Store latency sample

					latency_dict[symbol].append(latency_sec)

					# Once enough samples are collected, evaluate median

					if len(latency_dict[symbol]) >= LATENCY_SAMPLE_MIN:

						median = statistics.median(latency_dict[symbol])
						median_latency_dict[symbol] = median

						# Check if all symbols have valid latency below threshold

						if all(
							len(latency_dict[s]) >= LATENCY_SAMPLE_MIN and
							statistics.median(latency_dict[s]) < LATENCY_THRESHOLD_SEC
							for s in SYMBOLS
						):
							if not event_latency_valid.is_set():
								event_latency_valid.set()
								logger.info("Latency OK — all symbols within threshold. Event set.")

		except Exception as e:

			reconnect_attempt += 1
			logger.warning(f"WebSocket connection error (attempt {reconnect_attempt}): {e}")

			# Reset signal and buffers

			event_latency_valid.clear()

			for symbol in SYMBOLS:
				latency_dict[symbol].clear()
				depth_update_id_dict[symbol] = 0

			# Compute exponential backoff

			backoff_sec = (
				min(MAX_BACKOFF, BASE_BACKOFF * (2 ** reconnect_attempt))
				+ random.uniform(0, 1)
			)

			if reconnect_attempt > RESET_CYCLE_AFTER:

				reconnect_attempt = RESET_BACKOFF_LEVEL

			logger.warning(
				f"Retrying in {backoff_sec:.1f} seconds (attempt {reconnect_attempt})..."
			)

			await asyncio.sleep(backoff_sec)

		finally:

			logger.info("WebSocket connection closed.")

# ────────────────────────────────────────────────────────
# 🧩 Depth20 Snapshot Collector — Streams → Queue Buffer
# ────────────────────────────────────────────────────────

async def put_snapshot() -> None:

	"""
	🔁 Snapshot Streamer via Binance @depth20@100ms

	This coroutine connects to the Binance WebSocket stream for the
	top-20 order book (`@depth20@100ms`) and continuously extracts 
	symbol_snapshots_to_render for each tracked symbol.

	Behavior:
	- Waits until latency is acceptable (`event_stream_enable` is set).
	- For each message:
		• Parses symbol and bid/ask levels.
		• Applies median latency correction to compute event timestamp.
		• Stores the snapshot in memory (`symbol_snapshots_to_render`).
		• Pushes (symbol, snapshot) into `snapshots_queue` for persistence.
	- If the stream breaks, retries with exponential backoff + jitter.

	Note:
	- This stream does NOT include server-side timestamps ("E" field),
	  so all timing relies on client receipt time corrected by median latency.
	- Operates only when latency quality is trusted.
	"""
	
	global median_latency_dict, snapshots_queue
	attempt = 0  # Retry counter for reconnects

	while True:

		# ⏸ Wait until latency gate is open

		await event_stream_enable.wait()

		try:

			# 🔌 Connect to Binance combined stream (depth20@100ms)

			async with websockets.connect(WS_URL) as ws:

				logger.info(
					f"Connected to:\n"
					f"\t{WS_URL} (depth20@100ms)"
				)

				attempt = 0  # Reset retry count

				# 🔄 Process stream messages

				async for raw in ws:

					# 📦 Parse WebSocket message
					
					msg 	= json.loads(raw)
					stream	= msg.get("stream", "")
					symbol	= stream.split("@", 1)[0].lower()

					if symbol not in SYMBOLS:
						continue  # Skip unexpected symbols

					# ✅ Enforce latency gate per-symbol
					
					if not event_stream_enable.is_set() or not latency_dict[symbol]:
						continue  # Skip if latency is untrusted

					data		= msg.get("data", {})
					last_update = data.get("lastUpdateId")

					if last_update is None:
						continue  # Ignore malformed updates

					bids = data.get("bids", [])
					asks = data.get("asks", [])

					# 📝 Binance partial streams like @depth20@100ms do NOT include
					# the server-side event timestamp ("E"). Therefore, we must rely
					# on local receipt time corrected by estimated network latency.
					
					# 🎯 Estimate event timestamp via median latency compensation
					med_latency		= int(median_latency_dict.get(symbol, 0.0))		# in ms
					client_time_sec	= int(time.time() * 1_000)
					event_ts		= client_time_sec - med_latency	  # adjusted event time

					# 🧾 Construct snapshot
					snapshot = {
						"lastUpdateId": last_update,
						"eventTime": event_ts,
						"bids": [[float(p), float(q)] for p, q in bids],
						"asks": [[float(p), float(q)] for p, q in asks],
					}

					# 📤 Push to downstream queue for file dump

					await snapshots_queue.put((symbol, snapshot))

					# 🧠 Cache to in-memory store

					symbol_snapshots_to_render[symbol] = snapshot

					# 🔓 Signal FastAPI readiness after first snapshot

					if not ready_event.is_set():
						ready_event.set()

		except Exception as e:

			# ⚠️ On error: log and retry with backoff

			attempt += 1
			logger.warning(f"WebSocket error (attempt {attempt}): {e}")
			backoff = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 1)

			if attempt > RESET_CYCLE_AFTER:

				attempt = RESET_BACKOFF_LEVEL

			logger.warning(f"Retrying in {backoff:.1f} seconds...")

			await asyncio.sleep(backoff)

		finally:
			
			logger.info("WebSocket connection closed.")

# ───────────────────────────────
# 📝 Background Task: Save to File
# ───────────────────────────────

async def dump_snapshot():

	"""
	Asynchronous background writer loop:
	Consumes (symbol, snapshot) tuples from the `snapshots_queue`,
	saves them into date/interval-partitioned `.jsonl` files,
	and performs zip + cleanup + merge operations when the UTC+0 date changes.

	Behavior:
	- Saves each snapshot into a file named: `{SYMBOL}_orderbook_{SUFFIX}.jsonl`
	- One file per `symbol` and `SAVE_INTERVAL_MIN`
	- Files reside under: `./data/binance/orderbook/temporary/{SYMBOL}_orderbook_{YYYY-MM-DD}/`
	- On date change, triggers `merge + compression` for the previous date's data

	Note:
	- This function is intended to be started via `asyncio.create_task(dump_snapshot())`
	- Uses in-memory handle tracking (file_handles) to keep appends open per symbol
	"""

	global snapshots_queue

	while True:

		# put_snapshot()  → await snapshots_queue.put((symbol, snapshot))
		# dump_snapshot() → symbol, snapshot = await snapshots_queue.get()

		symbol, snapshot = await snapshots_queue.get()

		# ── Determine filename suffix (by interval) and date string

		event_ts_ms = snapshot.get("eventTime", int(time.time() * 1000))
		suffix		= get_file_suffix(SAVE_INTERVAL_MIN, event_ts_ms)
		day_str		= get_date_from_suffix(suffix)
		
		filename = f"{symbol.upper()}_orderbook_{suffix}.jsonl"

		# ── Ensure intermediate directory exists

		tmp_dir   = os.path.join(LOB_DIR, "temporary", f"{symbol.upper()}_orderbook_{day_str}")
		os.makedirs(tmp_dir, exist_ok=True)
		file_path = os.path.join(tmp_dir, filename)

		# ── Lookup or create write handle

		last_suffix, writer = file_handles.get(symbol, (None, None))

		# ── If the day rolled over: spawn async merge+compress of previous day

		if last_suffix and get_date_from_suffix(last_suffix) != day_str:

			threading.Thread(
				target=merge_all_symbols_for_day,
				args=(SYMBOLS, get_date_from_suffix(last_suffix))
			).start()

		# ── If suffix (time window) changed: rotate file writer

		if last_suffix != suffix:

			if writer:
				writer.close()
				zip_and_remove(os.path.join(tmp_dir, f"{symbol.upper()}_orderbook_{last_suffix}.jsonl"))

			writer = open(file_path, "a", encoding="utf-8")
			file_handles[symbol] = (suffix, writer)

		# ── Append snapshot JSON line
		
		line = json.dumps(snapshot, separators=(",", ":"))
		writer.write(line + "\n")
		writer.flush()

# ───────────────────────────────
# 🔍 Healthcheck Endpoints
# ───────────────────────────────

@app.get("/health/live")
async def health_live():
	"""
	Liveness probe — Returns 200 OK unconditionally.
	Used to check if the server process is alive (not necessarily functional).
	"""
	return {"status": "alive"}

@app.get("/health/ready")
async def health_ready():
	"""
	Readiness probe — Returns 200 OK only after first market snapshot is received.

	Before readiness:
		- Server may be running, but not yet connected to Binance stream.
		- Kubernetes/monitoring agents can use this to delay traffic routing.
	"""
	if ready_event.is_set():
		return {"status": "ready"}
	raise HTTPException(status_code=503, detail="not ready")

# ───────────────────────────────
# 🧠 JSON API for Order Book
# ───────────────────────────────

@app.get("/state/{symbol}")
async def get_order_book(symbol: str):
	"""
	Returns the most recent full order book snapshot (depth20) for a given symbol.

	Args:
		symbol (str): Trading pair symbol (e.g., "btcusdt").

	Returns:
		JSONResponse: Snapshot containing lastUpdateId, eventTime, bids, and asks.

	Raises:
		HTTPException 404 if the requested symbol is not being tracked.
	"""
	symbol = symbol.lower()

	if symbol not in symbol_snapshots_to_render:
		raise HTTPException(status_code=404, detail="symbol not found")

	return JSONResponse(content=symbol_snapshots_to_render[symbol])

# ───────────────────────────────
# 👁️ HTML UI for Order Book
# ───────────────────────────────
@app.get("/orderbook/{symbol}", response_class=HTMLResponse)
async def orderbook_ui(request: Request, symbol: str):
	"""
	Renders a lightweight HTML page showing the current order book snapshot for the given symbol.

	Args:
		request (Request): FastAPI request context (used for templating).
		symbol (str): Trading pair symbol (e.g., "btcusdt").

	Returns:
		Jinja2-rendered HTMLResponse of `orderbook.html` with top 20 bids and asks.

	Raises:
		HTTPException 404 if the requested symbol is not available in memory.
	"""
	sym = symbol.lower()

	if sym not in symbol_snapshots_to_render:
		raise HTTPException(status_code=404, detail="symbol not found")

	data = symbol_snapshots_to_render[sym]
	bids = data["bids"]
	asks = data["asks"]
	max_len = max(len(bids), len(asks))  # For consistent rendering in the template

	return templates.TemplateResponse(
		"orderbook.html",
		{
			"request": request,
			"symbol": sym,
			"bids": bids,
			"asks": asks,
			"max_len": max_len,
		},
	)

if __name__ == "__main__":

	import asyncio
	from uvicorn.config import Config
	from uvicorn.server import Server

	async def main():

		# Initialize in-memory structures
		global ready_event, snapshots_queue, depth_update_id_dict, median_latency_dict
		global latency_dict, event_latency_valid, event_stream_enable
		snapshots_queue = asyncio.Queue()
		latency_dict = {symbol: deque(maxlen=LATENCY_DEQUE_SIZE) for symbol in SYMBOLS}
		median_latency_dict = {symbol: 0.0 for symbol in SYMBOLS}
		depth_update_id_dict = {symbol: 0 for symbol in SYMBOLS}
		ready_event = asyncio.Event()
		event_latency_valid = asyncio.Event()
		event_stream_enable = asyncio.Event()
		event_stream_enable.clear()

		# Launch background tasks
		asyncio.create_task(dump_snapshot())				# Handles periodic snapshot persistence
		asyncio.create_task(put_snapshot())			# Streams and stores depth20@100ms symbol_snapshots_to_render
		asyncio.create_task(estimate_latency_via_diff_depth())		# Streams @depth for latency estimation
		asyncio.create_task(gate_streaming_by_latency())  		# Synchronize latency control

		# Wait for at least one valid snapshot before serving
		await ready_event.wait()

		# FastAPI
		logger.info(
			f"FastAPI server starts. Try:\n"
			f"\thttp://localhost:8000/orderbook/{SYMBOLS[0]}"
		)
		cfg = Config(app=app, host="0.0.0.0", port=8000, lifespan="off", use_colors=False)
		server = Server(cfg)
		await server.serve()

	asyncio.run(main())

# %%
