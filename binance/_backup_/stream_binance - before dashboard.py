# stream_binance.py
# Refer to RULESET.md for coding guidelines.

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

....................................................................................

Dependency:
	Python ≥ 3.9
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	jinja2==3.1.3
	yappi==1.6.10

Functionality:
	Stream Binance depth20 order books (100ms interval) via combined websocket.
	Maintain top-20 in-memory `symbol_snapshots_to_render` for each symbol.
	Periodically persist `symbol_snapshots_to_render` to JSONL → zip → aggregate daily.
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
			
....................................................................................

Binance Official GitHub Manual:
	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

................................................................................."""

# ───────────────────────────────────────────────────────────────────────────────
# 📦 Built-in Standard Library Imports (Grouped by Purpose)
# ───────────────────────────────────────────────────────────────────────────────

import asyncio, threading, time, random		# Async & Scheduling
import sys, os, shutil, zipfile				# File I/O & Path
import json, statistics						# Data Processing
from collections import deque
from io import TextIOWrapper
from typing import Dict, Deque
import atexit								# Exit Hook (for profiler result dump)

# ───────────────────────────────────────────────────────────────────────────────
# 📝 Logging Configuration: Rotating log file + console output with UTC timestamps
# ───────────────────────────────────────────────────────────────────────────────

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

# ───────────────────────────────────────────────────────────────────────────────
# 👤 Custom Formatter: Ensures all log timestamps are in UTC
# ───────────────────────────────────────────────────────────────────────────────

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

# ───────────────────────────────────────────────────────────────────────────────
# ⚙️ Formatter Definition (applied to both file and console)
# ───────────────────────────────────────────────────────────────────────────────

log_formatter = UTCFormatter("[%(asctime)s] %(levelname)s: %(message)s")

# ───────────────────────────────────────────────────────────────────────────────
# 💾 Rotating File Handler Configuration
# - Log file: stream_binance.log
# - Rotation: 10 MB per file
# - Retention: up to 3 old versions (e.g., .1, .2, .3)
# ───────────────────────────────────────────────────────────────────────────────

file_handler = RotatingFileHandler(
	"stream_binance.log",
	maxBytes	= 10_000_000,	# Rotate after 10 MB
	backupCount	= 100			# Keep 3 backups
)

try:

	file_handler.setFormatter(log_formatter)

except Exception as e:

	# Logging is not fully initialized yet, so use stderr directly.

	print(
		f"[{datetime.now(timezone.utc).isoformat()}] ERROR: "
		f"[global] Failed to set formatter for file_handler: {e}",
		file=sys.stderr
	)
	sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 📺 Console Handler Configuration
# - Mirrors the same UTC timestamp format
# ───────────────────────────────────────────────────────────────────────────────

console_handler = logging.StreamHandler()

try:

	console_handler.setFormatter(log_formatter)

except Exception as e:

	# Logging is not fully initialized yet, so use stderr directly.

	print(
		f"[{datetime.now(timezone.utc).isoformat()}] ERROR: "
		f"[global] Failed to set formatter for console_handler: {e}",
		file=sys.stderr
	)

	sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 🧠 Logger Setup & Handler Integration
# Unified logging for FastAPI, Uvicorn, websockets, and all dependencies.
# All logs are routed to both file and console with UTC timestamps.
# ───────────────────────────────────────────────────────────────────────────────

try:

	# Root logger: attach file and console handlers

	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	logger.addHandler(file_handler)
	logger.addHandler(console_handler)

	# Ensure third-party loggers propagate to root

	for name in [
		"websockets",
		"websockets.server",
		"websockets.client",
		"uvicorn",
		"uvicorn.error",
		"uvicorn.access",
		"fastapi",
		"starlette",
		"asyncio",
		"concurrent.futures"
	]:

		individual_logger = logging.getLogger(name)
		individual_logger.propagate = True
		individual_logger.setLevel(logging.INFO)

		for handler in individual_logger.handlers:
			handler.setFormatter(log_formatter)

except Exception as e:

	print(
		f"[{datetime.now(timezone.utc).isoformat()}] ERROR: "
		f"[global] Failed to initialize logging: {e}",
		file=sys.stderr
	)

	sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 📦 Third-Party Dependencies (from requirements.txt)
# ───────────────────────────────────────────────────────────────────────────────

# 📡 CORE ──────────────────────────────────────────────────────────────────────
# websockets:
#   - Core dependency for Binance L2 stream (`depth20@100ms`)
#   - Absolutely required for order book ingestion

import websockets

# 🌐 FastAPI Runtime Backbone ──────────────────────────────────────────────────
# FastAPI:
#   - Lightweight ASGI framework used as core runtime environment
#   - Powers both REST API endpoints and underlying logging system via `uvicorn`
#   - Enables HTTP access for:
#	   • /state/{symbol}		→ latest order book snapshot (JSON)
#	   • /orderbook/{symbol}	→ real-time bid/ask viewer (HTML)
#	   • /health/live, /ready   → liveness & readiness probes
#   - Logging is routed via `uvicorn.error`, so FastAPI is integral even
#	 when HTML rendering is not used.
# ⚠️ Removal of FastAPI implies rewriting logging + API infrastructure
# jinja2 (via FastAPI templates):
#   - Optional HTML rendering for order book visualization

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ───────────────────────────────────────────────────────────────────────────────
# 🧪 Profiling & Performance Diagnostics
# ───────────────────────────────────────────────────────────────────────────────

import yappi						# Coroutine-aware profiler

# ───────────────────────────────────────────────────────────────────────────────
# 📁 Utility: PyInstaller-Compatible Resource Resolver
# ───────────────────────────────────────────────────────────────────────────────

def resource_path(relative_path: str) -> str:

	"""
	───────────────────────────────────────────────────────────────────────────────
	🚨 DO NOT MODIFY THIS FUNCTION UNLESS NECESSARY.
	───────────────────────────────────────────────────────────────────────────────
	This function has been carefully designed and tested to resolve resource paths
	across PyInstaller builds, Docker containers, and OS differences (Windows ↔ Linux).
	Only update if new resource inclusion fails under current logic.

	───────────────────────────────────────────────────────────────────────────────
	📦 Purpose
	───────────────────────────────────────────────────────────────────────────────
	Resolve an absolute filesystem path to bundled resource files (e.g., templates,
	config files), ensuring compatibility with both:

	• 🧪 Development mode  — source-level execution on Windows
	• 🐧 Deployment mode   — PyInstaller-frozen binary on Ubuntu Linux

	───────────────────────────────────────────────────────────────────────────────
	⚠️ Runtime Environment Warning
	───────────────────────────────────────────────────────────────────────────────
	This project is built and distributed as a self-contained Linux binary using
	PyInstaller inside a Docker container (see Dockerfile).

	At runtime, all bundled files are extracted to a temporary directory, typically
	located at `/tmp/_MEIxxxx`, and made available via `sys._MEIPASS`.

	To support both dev and production execution seamlessly, this function resolves
	the correct base path at runtime.

	───────────────────────────────────────────────────────────────────────────────
	Args:
	───────────────────────────────────────────────────────────────────────────────
		relative_path (str):
			Path relative to this script — e.g.,
			• "template/"				 → for HTML rendering
			• "get_binance_chart.conf"   → chart API config

	Returns:
		str:
			Absolute path to the resource file, portable across environments.
	"""

	logger.info(f"[resource_path] Called with relative_path='{relative_path}'")

	try:

		base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))

		return os.path.join(base, relative_path)

	except Exception as e:

		logger.error(
			f"[resource_path] Failed to resolve path for '{relative_path}': {e}",
			exc_info=True
		)

		return None

# Bind template directory (used for rendering HTML order book UI)
# `resource_path()` ensures compatibility with PyInstaller-frozen Linux binaries.

templates_dir = resource_path("templates")

if templates_dir is None:

	logger.error(
		"[global] Failed to resolve template directory path for 'templates'. "
		"Application cannot start."
	)

	sys.exit(1)

templates = Jinja2Templates(directory=templates_dir)

# ───────────────────────────────────────────────────────────────────────────────
# ⚙️ Configuration Loader (.conf)
# ───────────────────────────────────────────────────────────────────────────────
# Shared configuration file used by both `stream_binance.py` and
# `get_binance_chart.py`, defining key runtime parameters such as:
#
#   • SYMBOLS			  → Binance symbols to stream (e.g., BTCUSDT)
#   • SAVE_INTERVAL_MIN	→ File rotation interval for snapshot persistence
#   • LOB_DIR			  → Output directory for JSONL and ZIP files
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
#
# 🛠️ NOTE:
# This loader assumes the config file is always present and correctly formed.
# If the file is missing or malformed, the app logs an error but continues.
# Currently, SYMBOLS=None triggers a runtime failure downstream.
# Consider fallback defaults or graceful shutdown logic in future revisions
# if robustness across missing config scenarios becomes important.
# ───────────────────────────────────────────────────────────────────────────────

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

		logger.error(
			f"[load_config] Failed to load config from '{conf_path}': {e}",
			exc_info=True
		)

		logger.error(f"Failed to load config from {conf_path}: {e}")

		sys.exit(1)

# 🔧 Load config via resource_path() for PyInstaller compatibility

conf_abs_path = resource_path(CONFIG_PATH)

if conf_abs_path is None:

	logger.error(
		f"[global] Failed to resolve config path for '{CONFIG_PATH}'. "
		f"Application cannot start."
	)

	sys.exit(1)

load_config(conf_abs_path)

# ───────────────────────────────────────────────────────────────────────────────
# 📊 Stream Parameters Derived from Config
# ───────────────────────────────────────────────────────────────────────────────
# Parse symbol and latency settings from .conf, and derive:
#   • `WS_URL` for combined Binance L2 depth20@100ms stream
#   • Tracking dicts for latency and update consistency

SYMBOLS = [s.lower() for s in CONFIG.get("SYMBOLS", "").split(",") if s.strip()]

if not SYMBOLS:

	logger.error(
		"[global] No SYMBOLS loaded from config. "
		"Check 'get_binance_chart.conf'. Application cannot start."
	)

	sys.exit(1)

STREAMS_PARAM	= "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL			= f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

# ───────────────────────────────────────────────────────────────────────────────
# 📈 Latency Measurement Parameters
# These control how latency is estimated from the @depth stream:
#   - LATENCY_DEQUE_SIZE:	 buffer size for per-symbol latency samples
#   - LATENCY_SAMPLE_MIN:	 number of samples required before validation
#   - LATENCY_THRESHOLD_SEC: max latency allowed for stream readiness
#   - ASYNC_SLEEP_INTERVAL:  Seconds to sleep in asyncio tasks
# ───────────────────────────────────────────────────────────────────────────────

LATENCY_DEQUE_SIZE	  = int(CONFIG.get("LATENCY_DEQUE_SIZE",	  10))
LATENCY_SAMPLE_MIN	  = int(CONFIG.get("LATENCY_SAMPLE_MIN",	  10))
LATENCY_THRESHOLD_SEC = float(CONFIG.get("LATENCY_THRESHOLD_SEC", 0.5))
LATENCY_SIGNAL_SLEEP  = float(CONFIG.get("LATENCY_SIGNAL_SLEEP",  0.2))
ASYNC_SLEEP_INTERVAL  = float(CONFIG.get("LATENCY_GATE_SLEEP",	  1.0))

# ────────────────────────────────────────────────────────────────────────────────────
# 🔄 WebSocket Ping/Pong Timing (from .conf)
# Controls client ping interval and pong timeout for Binance streams.
# Set to None to disable client pings (Binance pings the client by default).
# See Section `WebSocket Streams for Binance (2025-01-28)` in
# 	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
# ────────────────────────────────────────────────────────────────────────────────────

WS_PING_INTERVAL = int(CONFIG.get("WS_PING_INTERVAL", 0))
WS_PING_TIMEOUT  = int(CONFIG.get("WS_PING_TIMEOUT",  0))

if WS_PING_INTERVAL == 0: WS_PING_INTERVAL = None
if WS_PING_TIMEOUT  == 0: WS_PING_TIMEOUT  = None

# ───────────────────────────────────────────────────────────────────────────────
# 🧠 Runtime Per-Symbol State
#
# Maintains:
#   • LATENCY_DICT: Deque of recent latency samples per symbol
# 	  (used to compute median)
#   • MEDIAN_LATENCY_DICT: Cached median latency in milliseconds
# 	  per symbol
#   • DEPTH_UPDATE_ID_DICT: Latest `updateId` seen per symbol
# 	  from diff-depth streams
#
# Used to:
#   - Reject out-of-order updates
#   - Enable event stream only after latency stabilization
#   - Apply median latency compensation in absence of
# 	  server timestamps
# ───────────────────────────────────────────────────────────────────────────────

LATENCY_DICT:		  Dict[str, Deque[float]] = {}
MEDIAN_LATENCY_DICT:  Dict[str, float] = {}
DEPTH_UPDATE_ID_DICT: Dict[str, int] = {}
	
# ───────────────────────────────────────────────────────────────────────────────
# 🔒 Global Event Flags (pre-declared to prevent NameError)
# ───────────────────────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────────────────────
# 🔒 Global Event Flags (pre-declared to prevent NameError)
# - Properly initialized inside `main()` to bind to the right loop
# - ✅ Minimalistic pattern for single-instance runtime
# - ⚠️ Consider `AppContext` encapsulation
# 	if modularization/multi-instance is needed
# ───────────────────────────────────────────────────────────────────────────────

READY_EVENT:		 asyncio.Event
EVENT_LATENCY_VALID: asyncio.Event
EVENT_STREAM_ENABLE: asyncio.Event

EVENT_FLAGS_INITIALIZED = False

def initialize_event_flags():

	"""
	Initializes global asyncio.Event flags for controlling stream state.
	Logs any exception and terminates if initialization fails.
	"""

	try:

		global READY_EVENT, EVENT_LATENCY_VALID, EVENT_STREAM_ENABLE
		global EVENT_FLAGS_INITIALIZED

		READY_EVENT = asyncio.Event()
		EVENT_LATENCY_VALID = asyncio.Event()
		EVENT_STREAM_ENABLE = asyncio.Event()

		EVENT_FLAGS_INITIALIZED = True

		logger.info("[initialize_event_flags] Event flags initialized.")

	except Exception as e:

		logger.error(
			"[initialize_event_flags] Failed to initialize event flags: "
			f"{e}",
			exc_info=True
		)

		sys.exit(1)

def assert_event_flags_initialized():

	"""
	Asserts that event flags have been initialized.
	Logs and terminates if not initialized.
	"""

	if not EVENT_FLAGS_INITIALIZED:

		logger.error(
			"[assert_event_flags_initialized] Event flags not initialized. "
			"Call initialize_event_flags() before using event objects."
		)

		sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 🕒 Backoff Strategy & Snapshot Save Policy
# Configures:
#   • WebSocket reconnect behavior (exponential backoff)
#   • Order book snapshot directory and save intervals
#   • Optional data purging upon date rollover
# ───────────────────────────────────────────────────────────────────────────────

try:

	BASE_BACKOFF		= int(CONFIG.get("BASE_BACKOFF", 2))
	MAX_BACKOFF		 = int(CONFIG.get("MAX_BACKOFF", 30))
	RESET_CYCLE_AFTER   = int(CONFIG.get("RESET_CYCLE_AFTER", 7))
	RESET_BACKOFF_LEVEL = int(CONFIG.get("RESET_BACKOFF_LEVEL", 3))

	LOB_DIR = CONFIG.get("LOB_DIR", "./data/binance/orderbook/")

	PURGE_ON_DATE_CHANGE= int(CONFIG.get("PURGE_ON_DATE_CHANGE", 1))
	SAVE_INTERVAL_MIN   = int(CONFIG.get("SAVE_INTERVAL_MIN", 1440))

	if SAVE_INTERVAL_MIN > 1440:

		raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

except Exception as e:

	logger.error(
		f"[global] Failed to load or validate stream/save config: {e}",
		exc_info=True
	)
	
	sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 🧪 Optional Profiling (Controlled via .conf)
# Configures:
#   • Execution duration in seconds for profiling with `yappi`
#   • If 0 → profiling is disabled, runs indefinitely
# ───────────────────────────────────────────────────────────────────────────────

try:

	PROFILE_DURATION = int(CONFIG.get("PROFILE_DURATION", 0))

	# Ensure order book directory exists

	os.makedirs(LOB_DIR, exist_ok=True)

except Exception as e:

	logger.error(
		"[global] Failed to set up profiling or create order book directory: "
		f"{e}",
		exc_info=True
	)

	sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 📦 Runtime Memory Buffers & Async File Handles
#
# Maintains symbol-specific runtime state for:
#   • Snapshot ingestion (queue per symbol)
#   • API rendering (in-memory latest snapshot)
#   • File writing (active handle per symbol)
#   • Daily merge deduplication (date set)
#
# Structures:
#
#   SNAPSHOTS_QUEUE_DICT: dict[str, asyncio.Queue[dict]]
#	 → Per-symbol async queues storing order book snapshots pushed
#	   by `put_snapshot()` and consumed by `dump_snapshot_for_symbol()`.
#
#   symbol_snapshots_to_render: dict[str, dict]
#	 → In-memory latest snapshot per symbol for API rendering via FastAPI.
#	   Used only for testing/debug visualization; not persisted to disk.
#
#   SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]]
#	 → Tracks open file writers per symbol:
#		└── (last_suffix, writer) where:
#			• last_suffix: str = time suffix like "2025-07-03_15-00"
#			• writer: open text file handle for appending .jsonl data
#
#   MERGED_DAYS: set[str]
#	 → Contains UTC day strings ("YYYY-MM-DD") that have already been
#	   merged+compressed to prevent duplicate merge threads.
#
#   MERGE_LOCKS: `threading.Lock` per SYMBOL
#	 → Prevents race condition on `MERGED_DAYS` during concurrent
#	   merge launches from multiple symbol writers.
# ───────────────────────────────────────────────────────────────────────────────

SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}
symbol_snapshots_to_render: dict[str, dict] = {}
SYMBOL_TO_FILE_HANDLES:		dict[str, tuple[str, TextIOWrapper]] = {}

# Each symbol has its own threading.Lock to ensure
# independent synchronization during merge operations.

MERGED_DAYS: set[str] = set()
MERGE_LOCKS: dict[str, threading.Lock] = {
	symbol: threading.Lock() for symbol in SYMBOLS
}

def initialize_runtime_state():

	"""
	Initializes all global runtime state dictionaries and sets.
	Logs and terminates if any error occurs during initialization.
	"""

	try:
		global SYMBOLS
		global LATENCY_DICT, MEDIAN_LATENCY_DICT, DEPTH_UPDATE_ID_DICT
		global SNAPSHOTS_QUEUE_DICT

		LATENCY_DICT.clear()
		LATENCY_DICT.update({
			symbol: deque(maxlen=LATENCY_DEQUE_SIZE)
			for symbol in SYMBOLS
		})

		MEDIAN_LATENCY_DICT.clear()
		MEDIAN_LATENCY_DICT.update({
			symbol: 0.0
			for symbol in SYMBOLS
		})

		DEPTH_UPDATE_ID_DICT.clear()
		DEPTH_UPDATE_ID_DICT.update({
			symbol: 0
			for symbol in SYMBOLS
		})

		SNAPSHOTS_QUEUE_DICT.clear()
		SNAPSHOTS_QUEUE_DICT.update({
			symbol: asyncio.Queue() for symbol in SYMBOLS
		})

		symbol_snapshots_to_render.clear()
		symbol_snapshots_to_render.update({
			symbol: {}
			for symbol in SYMBOLS
		})

		SYMBOL_TO_FILE_HANDLES.clear()
		MERGED_DAYS.clear()

		logger.info("[initialize_runtime_state] Runtime state initialized.")

	except Exception as e:
		logger.error(
			"[initialize_runtime_state] Failed to initialize runtime state: "
			f"{e}",
			exc_info=True
		)
		sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 📦 File Utilities: Naming, Compression, and Periodic Merging
#
# Includes:
#   • get_file_suffix(...) → Returns time window suffix for
# 	  filenames (e.g., '1315' for 13:15 UTC)
#   • zip_and_remove(...) → Compresses a file into .zip and
# 	  deletes the original
#   • merge_day_zips_to_single_jsonl(...) → Merges minute-level
# 	  .zip files into daily .jsonl archive
#
# Note:
#   - Merging behavior assumes SAVE_INTERVAL_MIN < 1440
# 	  (i.e., per-day rollover is supported)
#   - If SAVE_INTERVAL_MIN == 1440, merging is redundant but harmless
# ───────────────────────────────────────────────────────────────────────────────

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

	try:

		ts = datetime.utcfromtimestamp(event_ts_ms / 1000)

		if interval_min >= 1440:

			return ts.strftime("%Y-%m-%d")

		else:

			return ts.strftime("%Y-%m-%d_%H-%M")

	except Exception as e:

		logger.error(
			f"[get_file_suffix] Failed to generate suffix for "
			f"interval_min={interval_min}, event_ts_ms={event_ts_ms}: {e}",
			exc_info=True
		)

		return "invalid_suffix"

# .............................................................

def get_date_from_suffix(suffix: str) -> str:

	"""
	Extracts the date portion from a file suffix.

	Args:
		suffix (str): Filename suffix such as '2025-06-27_13-15'

	Returns:
		str: Date string in 'YYYY-MM-DD'
	"""

	try:

		return suffix.split("_")[0]

	except Exception as e:

		logger.error(
			f"[get_date_from_suffix] Failed to extract date "
			f"from suffix '{suffix}': {e}",
			exc_info=True
		)

		return "invalid_date"

# .............................................................

def zip_and_remove(src_path: str):

	"""
	Zips the specified .jsonl file and removes the original.

	Args:
		src_path (str): Path to the JSONL file to compress
	"""

	try:

		if os.path.exists(src_path):

			zip_path = src_path.replace(".jsonl", ".zip")

			with zipfile.ZipFile(
				zip_path, "w", zipfile.ZIP_DEFLATED
			) as zf:

				zf.write(
					src_path,
					arcname=os.path.basename(src_path)
				)

			os.remove(src_path)

	except Exception as e:

		logger.error(
			f"[zip_and_remove] Failed to zip "
			f"or remove '{src_path}': {e}",
			exc_info=True
		)

# .............................................................

def merge_day_zips_to_single_jsonl(
	symbol:	  str,
	day_str:  str,
	base_dir: str,
	purge:	  bool = True
):

	"""
	🗃️ Merge Per-Minute Zips into Single Daily `.jsonl` Archive

	For a given trading `symbol` and `day_str`, this routine locates all `.zip` files
	under the corresponding temporary directory, unpacks and concatenates their
	contents into a single `.jsonl` file, then re-compresses it as a single zip archive.

	This consolidation serves long-term archival, reducing file system clutter and
	enabling efficient downstream loading.

	Fault tolerance: gracefully skips if temp folder or zip files are missing,
	or if some zips are corrupted or concurrently removed. Logs all errors.
	Never throws to caller.
	"""

	# Construct working directories and target paths

	tmp_dir = os.path.join(
		base_dir,
		"temporary",
		f"{symbol.upper()}_orderbook_{day_str}"
	)

	merged_path = os.path.join(
		base_dir,
		f"{symbol.upper()}_orderbook_{day_str}.jsonl"
	)

	# Abort early if directory is missing (no data captured for this day)

	if not os.path.isdir(tmp_dir):

		logger.info(
			f"[merge_day_zips] Temp dir missing for {symbol} on {day_str}: {tmp_dir}"
		)
		return

	# List all zipped minute-level files (may be empty)

	try:

		zip_files = [f for f in os.listdir(tmp_dir) if f.endswith(".zip")]

	except Exception as e:

		logger.warning(
			f"[merge_day_zips] Failed to list zips in {tmp_dir}: {e}",
			exc_info=True
		)

		return

	if not zip_files:

		logger.info(
			f"[merge_day_zips] No zip files to merge for {symbol} on {day_str}."
		)

		return

	try:

		# Open output file for merged .jsonl content

		try:

			with open(merged_path, "w", encoding="utf-8") as fout:

				# Process each zip file in chronological order

				for zip_file in sorted(zip_files):

					zip_path = os.path.join(tmp_dir, zip_file)

					try:

						with zipfile.ZipFile(zip_path, "r") as zf:

							for member in zf.namelist():

								with zf.open(member) as f:

									for raw in f:

										fout.write(raw.decode("utf-8") + "\n")

					except Exception as e:

						logger.error(
							f"[merge_day_zips] Failed to extract {zip_path}: {e}",
							exc_info=True
						)

						return

		except Exception as e:

			logger.error(
				f"[merge_day_zips] Failed to open or "
				f"write to merged file {merged_path}: {e}",
				exc_info=True

			)

			try:

				if fout: fout.close()

			except Exception as close_error:
				
				logger.warning(
					f"[merge_day_zips] Failed to close output file: {close_error}",
					exc_info=True
				)

			return

		finally:

			# Ensure the output file is closed

			try:

				if fout: fout.close()

			except Exception as close_error:

				logger.warning(
					f"[merge_day_zips] Failed to close output file: {close_error}",
					exc_info=True
				)

				return

			return

		# Recompress the consolidated .jsonl into a final single-archive zip

		try:

			final_zip = merged_path.replace(".jsonl", ".zip")

			with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:

				zf.write(merged_path, arcname=os.path.basename(merged_path))

		except Exception as e:

			logger.error(
				f"[merge_day_zips] Failed to compress merged file for {symbol} on {day_str}: {e}",
				exc_info=True
			)

			# Do not remove .jsonl if compression failed

			return

		# Remove intermediate plain-text .jsonl file after compression

		try:

			if os.path.exists(merged_path):

				os.remove(merged_path)

		except Exception as e:

			logger.warning(
				f"[merge_day_zips] Failed to remove merged .jsonl "
				f"for {symbol} on {day_str}: {e}",
				exc_info=True
			)

		# Optionally delete the original temp folder containing per-minute zips

		if purge:

			try:

				shutil.rmtree(tmp_dir)

			except Exception as e:

				logger.warning(
					f"[merge_day_zips] Failed to remove temp dir {tmp_dir}: {e}",
					exc_info=True
				)

	except FileNotFoundError as e:

		logger.warning(
			f"[merge_day_zips] No files found to merge "
			f"for {symbol} on {day_str}: {e}"
		)

		return

	except Exception as e:

		logger.error(
			f"[merge_day_zips] Unexpected error "
			f"merging {symbol} on {day_str}: {e}",
			exc_info=True
		)

		return

# .............................................................

def merge_all_symbols_for_day(symbols: list[str], day_str: str):

	"""
	Trigger parallel merge operations for each symbol
	for the given UTC+0 date.
	Each symbol's zipped snapshots are consolidated into
	a single `.jsonl` archive.

	Args:
		symbols (list[str]):
			List of trading symbols to merge
		day_str (str):
			Target UTC date string in "YYYY-MM-DD" format

	Note:
		- This function merely orchestrates per-symbol merges
		  via `merge_day_zips_to_single_jsonl()`.
		- Duplicate merge attempts must be avoided externally,
		  e.g., via `MERGED_DAYS`.
		- Can be safely invoked from multiple sources as long as
		external guards are applied.
	"""

	for symbol in symbols:

		try:

			merge_day_zips_to_single_jsonl(
				symbol,
				day_str,
				LOB_DIR,
				purge=(PURGE_ON_DATE_CHANGE == 1)
			)

		except Exception as e:

			logger.error(
				f"[merge_all_symbols_for_day] Failed to merge "
				f"for symbol '{symbol}' on '{day_str}': {e}",
				exc_info=True
			)

# ───────────────────────────────────────────────────────────────────────────────
# 🕓 Latency Control: Measurement, Thresholding, and Flow Gate
# ───────────────────────────────────────────────────────────────────────────────

async def gate_streaming_by_latency() -> None:

	"""
	Streaming controller based on latency.
	Manages EVENT_STREAM_ENABLE flag for order book streaming.
	Observes EVENT_LATENCY_VALID, set by latency estimation loop.
	"""

	has_logged_warmup = False  # Initial launch flag

	while True:

		try:

			# Check latency and streaming flags

			latency_passed = EVENT_LATENCY_VALID.is_set()
			stream_currently_on = EVENT_STREAM_ENABLE.is_set()
			has_any_latency = all(
				len(LATENCY_DICT[s]) > 0 for s in SYMBOLS
			)

			if latency_passed and not stream_currently_on:

				logger.info(
					"[gate_streaming_by_latency] "
					f"Latency normalized. "
					f"Enable order book stream."
				)

				EVENT_STREAM_ENABLE.set()
				has_logged_warmup = False

			elif not latency_passed:

				if not has_any_latency and not has_logged_warmup:

					logger.info(
						f"[gate_streaming_by_latency] "
						f"Warming up latency measurements..."
					)

					has_logged_warmup = True

				elif has_any_latency and stream_currently_on:

					logger.warning(
						f"[gate_streaming_by_latency] "
						f"Latency degraded. "
						f"Pausing order book stream."
					)

					EVENT_STREAM_ENABLE.clear()

			await asyncio.sleep(LATENCY_SIGNAL_SLEEP)

		except Exception as e:

			logger.error(
				"[gate_streaming_by_latency] "
				f"Exception in latency gate: "
				f"{e}",
				exc_info=True
			)

			await asyncio.sleep(LATENCY_GATE_SLEEP)

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
		• If all medians < `LATENCY_THRESHOLD_SEC`, sets `EVENT_LATENCY_VALID`.
		• If excessive latency or disconnection, clears the signal.

	Purpose:
	- `EVENT_LATENCY_VALID` acts as a global flow control flag.
	- Used by `gate_streaming_by_latency()` to pause/resume 
	order book streaming via `EVENT_STREAM_ENABLE`.

	Backoff:
	- On disconnection or failure, retries with exponential backoff and jitter.

	Notes:
	- This is **not** a true RTT (round-trip time) estimate.
	- But sufficient for gating real-time systems where latency 
	directly affects snapshot timestamp correctness.
	"""

	global LATENCY_DICT, MEDIAN_LATENCY_DICT, DEPTH_UPDATE_ID_DICT

	url = (
		"wss://stream.binance.com:9443/stream?"
		+ "streams=" + "/".join(f"{symbol}@depth" for symbol in SYMBOLS)
	)

	reconnect_attempt = 0

	while True:

		try:

			async with websockets.connect(
				url,
				ping_interval = WS_PING_INTERVAL,
				ping_timeout  = WS_PING_TIMEOUT
			) as ws:

				logger.info(
					f"[estimate_latency_via_diff_depth] "
					f"Connected to:\n{format_ws_url(url, '(@depth)')}\n"
				)

				reconnect_attempt = 0  # Reset retry counter

				async for raw_msg in ws:

					try:

						message = json.loads(raw_msg)
						data = message.get("data", {})
						server_event_ts_ms = data.get("E")

						if server_event_ts_ms is None:

							continue  # Drop malformed message

						stream_name = message.get("stream", "")
						symbol = stream_name.split("@", 1)[0].lower()

						if symbol not in SYMBOLS:

							continue  # Ignore unexpected symbols

						update_id = data.get("u")

						if update_id is None or update_id <= DEPTH_UPDATE_ID_DICT.get(symbol, 0):

							continue  # Duplicate or out-of-order update

						DEPTH_UPDATE_ID_DICT[symbol] = update_id
					
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

						LATENCY_DICT[symbol].append(latency_sec)

						if len(LATENCY_DICT[symbol]) >= LATENCY_SAMPLE_MIN:

							median = statistics.median(LATENCY_DICT[symbol])
							MEDIAN_LATENCY_DICT[symbol] = median

							if all(
								len(LATENCY_DICT[s]) >= LATENCY_SAMPLE_MIN and
								statistics.median(LATENCY_DICT[s]) < LATENCY_THRESHOLD_SEC
								for s in SYMBOLS
							):
								if not EVENT_LATENCY_VALID.is_set():

									EVENT_LATENCY_VALID.set()

									logger.info(
										"[estimate_latency_via_diff_depth] "
										f"Latency OK — all symbols within threshold. "
										f"Event set."
									)
					except Exception as e:

						logger.warning(
							f"[estimate_latency_via_diff_depth] "
							f"Failed to process message: {e}",
							exc_info=True
						)

						continue

		except Exception as e:

			reconnect_attempt += 1

			logger.warning(
				f"[estimate_latency_via_diff_depth] "
				f"WebSocket connection error (attempt {reconnect_attempt}): {e}",
				exc_info=True
			)

			EVENT_LATENCY_VALID.clear()

			for symbol in SYMBOLS:

				LATENCY_DICT[symbol].clear()
				DEPTH_UPDATE_ID_DICT[symbol] = 0

			backoff_sec = (
				min(MAX_BACKOFF, BASE_BACKOFF * (2 ** reconnect_attempt))
				+ random.uniform(0, 1)
			)

			if reconnect_attempt > RESET_CYCLE_AFTER:

				reconnect_attempt = RESET_BACKOFF_LEVEL

			logger.warning(
				f"[estimate_latency_via_diff_depth] "
				f"Retrying in {backoff_sec:.1f} seconds "
				f"(attempt {reconnect_attempt})..."
			)

			await asyncio.sleep(backoff_sec)

		finally:

			logger.info(
				f"[estimate_latency_via_diff_depth] "
				f"WebSocket connection closed."
			)

def format_ws_url(url: str, label: str = "") -> str:

	"""
	Formats a Binance WebSocket URL for multi-symbol readability.
	Example:
		wss://stream.binance.com:9443/stream?streams=
			btcusdc@depth/
			ethusdc@depth/
			solusdc@depth (@depth)
	"""

	if "streams=" not in url:

		return url + (f" {label}" if label else "")

	prefix, streams = url.split("streams=", 1)
	symbols = streams.split("/")
	formatted = "\t" + prefix + "streams=\n"
	formatted += "".join(f"\t\t{s}/\n" for s in symbols if s)
	formatted = formatted.rstrip("/\n")

	if label:

		formatted += f" {label}"

	return formatted

# ───────────────────────────────────────────────────────────────────────────────
# 🧩 Depth20 Snapshot Collector — Streams → Queue Buffer
# ───────────────────────────────────────────────────────────────────────────────

async def put_snapshot() -> None:

	"""
	🧩 Binance Depth20 Snapshot Collector → Per-Symbol Async Queue + Render Cache

	Continuously consumes top-20 order book snapshots from Binance WebSocket stream
	(`@depth20@100ms`) for all tracked symbols, applies latency compensation, and
	dispatches each processed snapshot into:
	• `SNAPSHOTS_QUEUE_DICT[symbol]` — for persistent file logging.
	• `symbol_snapshots_to_render[symbol]` — for live debug rendering via FastAPI.

	Behavior:
	• Waits for `EVENT_STREAM_ENABLE` to confirm latency quality.
	• For each stream message:
		- Extracts symbol, bid/ask levels, and last update ID.
		- Applies median-latency correction to compute `eventTime` (in ms).
		- Dispatches snapshot to both persistence queue and render cache.

	Notes:
	• This stream lacks Binance-provided timestamps ("E"); all timing
	  is client-side and latency-compensated.
	• `eventTime` is an `int` (milliseconds since UNIX epoch).
	• Only `SNAPSHOTS_QUEUE_DICT[symbol]` is used for durable storage.
	• `symbol_snapshots_to_render` is ephemeral and used exclusively
	  for internal diagnostics or FastAPI display.
	• On failure, reconnects with exponential backoff + jitter.
	"""

	global LATENCY_DICT, MEDIAN_LATENCY_DICT, SNAPSHOTS_QUEUE_DICT

	attempt = 0  # Retry counter for reconnects

	while True:

		# ⏸ Wait until latency gate is open

		await EVENT_STREAM_ENABLE.wait()

		try:

			# 🔌 Connect to Binance combined stream (depth20@100ms)

			async with websockets.connect(
				WS_URL,
				ping_interval = WS_PING_INTERVAL,
				ping_timeout  = WS_PING_TIMEOUT
			) as ws:

				logger.info(
					f"[put_snapshot] "
					f"Connected to:\n{format_ws_url(WS_URL, '(depth20@100ms)')}\n"
				)
				
				attempt = 0  # Reset retry count

				# 🔄 Process stream messages

				async for raw in ws:

					try:

						# 📦 Parse WebSocket message

						msg = json.loads(raw)
						stream = msg.get("stream", "")
						symbol = stream.split("@", 1)[0].lower()

						if symbol not in SYMBOLS:

							continue  # Skip unexpected symbols

						# ✅ Enforce latency gate per-symbol

						if not EVENT_STREAM_ENABLE.is_set() or not LATENCY_DICT[symbol]:

							continue  # Skip if latency is untrusted

						data = msg.get("data", {})
						last_update = data.get("lastUpdateId")

						if last_update is None:

							continue  # Ignore malformed updates

						bids = data.get("bids", [])
						asks = data.get("asks", [])

						# 📝 Binance partial streams like @depth20@100ms do NOT include
						# the server-side event timestamp ("E"). Therefore, we must rely
						# on local receipt time corrected by estimated network latency.

						# 🎯 Estimate event timestamp via median latency compensation

						med_latency = int(MEDIAN_LATENCY_DICT.get(symbol, 0.0))  # in ms
						client_time_sec = int(time.time() * 1_000)
						event_ts = client_time_sec - med_latency  # adjusted event time

						# 🧾 Construct snapshot

						snapshot = {
							"lastUpdateId": last_update,
							"eventTime": event_ts,
							"bids": [[float(p), float(q)] for p, q in bids],
							"asks": [[float(p), float(q)] for p, q in asks],
						}

						# 📤 Push to downstream queue for file dump

						await SNAPSHOTS_QUEUE_DICT[symbol].put(snapshot)

						# 🧠 Cache to in-memory store (just for debug-purpose rendering)

						symbol_snapshots_to_render[symbol] = snapshot

						# 🔓 Signal FastAPI readiness after first snapshot

						if not READY_EVENT.is_set():

							READY_EVENT.set()

					except Exception as e:

						logger.warning(
							f"[put_snapshot] Failed to process message: {e}",
							exc_info=True
						)

						continue

		except Exception as e:

			# ⚠️ On error: log and retry with backoff

			attempt += 1

			logger.warning(
				f"[put_snapshot] WebSocket error (attempt {attempt}): {e}",
				exc_info=True
			)

			backoff = min(
				MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt)
			) + random.uniform(0, 1)

			if attempt > RESET_CYCLE_AFTER:

				attempt = RESET_BACKOFF_LEVEL

			logger.warning(
				f"[put_snapshot] Retrying in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

		finally:

			logger.info("[put_snapshot] WebSocket connection closed.")

# ───────────────────────────────────────────────────────────────────────────────
# 📝 Background Task: Save to File
# ───────────────────────────────────────────────────────────────────────────────

async def dump_snapshot_for_symbol(symbol: str) -> None:

	"""
	📤 Per-Symbol Snapshot File Dumper (async, persistent, compressed)

	Continuously consumes snapshots from `SNAPSHOTS_QUEUE_DICT[symbol]`
	and appends them to per-symbol `.jsonl` files partitioned by time.
	When a UTC day rolls over, triggers merging/compression in a thread.

	Behavior:
	• For each snapshot:
		- Compute `suffix` (e.g., "1730") and `day_str` (e.g., "2025-07-03")
		- Ensure directory and file path for current interval exist
		- Append snapshot to: {symbol}_orderbook_{suffix}.jsonl
		- If suffix changes: rotate file handle
		- If day changes: start merge thread (with lock protection)

	Internal Structures:
	• `SYMBOL_TO_FILE_HANDLES[symbol] → (suffix, writer)`
		↳ Active file writer for the current time window.
	• `MERGED_DAYS` tracks which UTC days have been merged
	  to avoid launching redundant threads across symbols.
	• `MERGE_LOCKS` protect access to `MERGED_DAYS` to avoid
	  race conditions in multi-symbol contexts.

	Notes:
	• Runs forever via `asyncio.create_task(...)`
	• Flushes every snapshot to prevent memory loss
	• Merge is dispatched only once per UTC day
	"""

	global SYMBOL_TO_FILE_HANDLES, SNAPSHOTS_QUEUE_DICT
	global EVENT_STREAM_ENABLE

	queue = SNAPSHOTS_QUEUE_DICT[symbol]

	while True:

		# Block until new snapshot is received

		try:

			snapshot = await queue.get()

		except Exception as e:

			logger.error(
				f"[{symbol.upper()}] ❌ Failed to get snapshot from queue: {e}",
				exc_info=True
			)

			continue

		if not EVENT_STREAM_ENABLE.is_set():

			break

		# ── Compute suffix (time block) and day string (UTC)

		try:

			event_ts_ms	= snapshot.get("eventTime", int(time.time() * 1000))
			suffix		= get_file_suffix(SAVE_INTERVAL_MIN, event_ts_ms)
			day_str		= get_date_from_suffix(suffix)

		except Exception as e:

			logger.error(
				f"[{symbol.upper()}] ❌ Failed to compute suffix/day: {e}",
				exc_info=True
			)

			continue

		# ── Build filename and full path

		try:

			filename = f"{symbol.upper()}_orderbook_{suffix}.jsonl"
			tmp_dir = os.path.join(
				LOB_DIR,
				"temporary",
				f"{symbol.upper()}_orderbook_{day_str}",
			)
			os.makedirs(tmp_dir, exist_ok=True)
			file_path = os.path.join(tmp_dir, filename)

		except Exception as e:

			logger.error(
				f"[{symbol.upper()}] ❌ Failed to build file path: {e}",
				exc_info=True
			)

			continue

		# ── Retrieve last writer (if any)

		last_suffix, writer = SYMBOL_TO_FILE_HANDLES.get(symbol, (None, None))

		# ── Spawn merge thread if day has changed and not already merged

		try:

			if last_suffix:

				last_day = get_date_from_suffix(last_suffix)

				with MERGE_LOCKS[symbol]:

					# .....................................................
					# This block ensures thread-safe execution for
					# merge operations. The `MERGED_DAYS.add(last_day)`
					# and `threading.Thread(...)` calls are guaranteed
					# to execute only once per symbol and day combination.
					# Even if `merge_all_symbols_for_day` fails, the state
					# in `MERGED_DAYS` prevents redundant merge attempts
					# for the same day.
					# .....................................................

					if last_day != day_str and last_day not in MERGED_DAYS:

						MERGED_DAYS.add(last_day)

						threading.Thread(
							target=merge_all_symbols_for_day,
							args=(SYMBOLS, last_day),
						).start()

		except Exception as e:

			logger.warning(
				f"[{symbol.upper()}] ⚠️ Failed to spawn merge thread: {e}",
				exc_info=True
			)

		# ── Rotate writer if suffix (HHMM) window has changed

		if last_suffix != suffix:

			if writer:

				try:

					writer.close()

				except Exception as e:

					logger.warning(
						f"[{symbol.upper()}] ⚠️ Close failed → {e}",
						exc_info=True
					)

				try:
					zip_and_remove(
						os.path.join(
							tmp_dir,
							f"{symbol.upper()}_orderbook_{last_suffix}.jsonl"
						)
					)

				except Exception as e:

					logger.warning(
						f"[{symbol.upper()}] ⚠️ zip_and_remove failed: {e}",
						exc_info=True
					)

			try:

				writer = open(file_path, "a", encoding="utf-8")

			except OSError as e:

				logger.error(
					f"[{symbol.upper()}] ❌ Open failed: {file_path} → {e}",
					exc_info=True
				)

				continue  # Skip this snapshot

			SYMBOL_TO_FILE_HANDLES[symbol] = (suffix, writer)

		# ── Write snapshot as compact JSON line

		try:

			line = json.dumps(snapshot, separators=(",", ":"))
			writer.write(line + "\n")
			writer.flush()

		except Exception as e:

			logger.error(
				f"[{symbol.upper()}] ❌ Write failed: {file_path} → {e}",
				exc_info=True
			)

			# Invalidate writer for next iteration

			SYMBOL_TO_FILE_HANDLES.pop(symbol, None)

			continue

# ───────────────────────────────────────────────────────────────────────────────
# 🛑 Graceful Shutdown Handler (FastAPI Lifespan)
# Migrates from deprecated @app.on_event("shutdown") to lifespan context.
# Ensures all file writers are closed and data is safely flushed on shutdown.
# ───────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):

	"""
	FastAPI lifespan handler for graceful shutdown.

	On shutdown, closes all active file writers for each symbol to ensure
	all snapshot data is flushed and safely written to disk.
	This prevents data loss in case the application exits before
	individual file handles are rotated or closed.
	"""

	# Startup logic (if any) goes here

	yield

	# Shutdown logic: close all file writers

	for symbol in SYMBOLS:

		suffix_writer = SYMBOL_TO_FILE_HANDLES.get(symbol)
		
		if not suffix_writer:

			continue  # No writer was created for this symbol

		suffix, writer = suffix_writer

		try:

			if writer:

				writer.close()

			logger.info(
				f"[shutdown] Closed file for {symbol} (suffix: {suffix})"
			)

		except Exception as e:
			
			logger.error(
				f"[shutdown] Failed to close file for {symbol}: {e}",
				exc_info=True
			)

# ───────────────────────────────────────────────────────────────────────────────
# ⚙️ FastAPI Initialization + HTML Template Binding
# ───────────────────────────────────────────────────────────────────────────────
# FastAPI serves as the **core runtime backbone** for this application.
# It is not merely optional; several key subsystems depend on it:
#
#   1. 📊 Logging Integration:
#	  - Logging is routed via `uvicorn.error`, which is managed by FastAPI's ASGI server.
#	  - This means our logger (`logger = logging.getLogger("uvicorn.error")`) is **active**
#		and functional even before we explicitly launch the app, as long as FastAPI is imported.
#
#   2. 🌐 REST API Endpoints:
#	  - Used for health checks, JSON-based order book access, and real-time UI rendering.
#
#   3. 🧱 HTML UI Layer (Optional but Useful):
#	  - The Jinja2 template system is integrated via FastAPI to serve HTML at `/orderbook/{symbol}`.
#
# ⚠️ If FastAPI were removed, the following features would break:
#	 → Logging infrastructure
#	 → REST endpoints (/health, /state)
#	 → HTML visualization
#
# So although not all FastAPI features are always used, **its presence is structurally required**.

app = FastAPI(lifespan=lifespan)

# ───────────────────────────────────────────────────────────────────────────────
# 🔍 Healthcheck Endpoints
# ───────────────────────────────────────────────────────────────────────────────

@app.get("/health/live")
async def health_live():

	"""
	Liveness probe — Returns 200 OK unconditionally.
	Used to check if the server process is alive (not necessarily functional).
	"""

	try:

		return {"status": "alive"}

	except Exception as e:

		logger.error(
			f"[health_live] Healthcheck failed: {e}",
			exc_info=True
		)

		raise HTTPException(status_code=500, detail="healthcheck error")

@app.get("/health/ready")
async def health_ready():

	"""
	Readiness probe — Returns 200 OK only after first market snapshot is received.

	Before readiness:
		- Server may be running, but not yet connected to Binance stream.
		- Kubernetes/monitoring agents can use this to delay traffic routing.
	"""

	try:

		if READY_EVENT.is_set():

			return {"status": "ready"}

		raise HTTPException(status_code=503, detail="not ready")

	except Exception as e:

		logger.error(
			f"[health_ready] Readiness check failed: {e}",
			exc_info=True
		)

		raise HTTPException(status_code=500, detail="readiness check error")

# ───────────────────────────────────────────────────────────────────────────────
# 🧠 JSON API for Order Book
# ───────────────────────────────────────────────────────────────────────────────

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

	try:

		symbol = symbol.lower()

		if symbol not in symbol_snapshots_to_render:

			raise HTTPException(status_code=404, detail="symbol not found")

		return JSONResponse(content=symbol_snapshots_to_render[symbol])

	except Exception as e:

		logger.error(
			f"[get_order_book] Failed to serve order book for '{symbol}': {e}",
			exc_info=True
		)
		
		raise HTTPException(status_code=500, detail="internal error")

# ───────────────────────────────────────────────────────────────────────────────
# 👁️ HTML UI for Order Book
# ───────────────────────────────────────────────────────────────────────────────

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

	try:

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

	except HTTPException:

		raise

	except Exception as e:

		logger.error(
			f"[orderbook_ui] Failed to render order book for '{symbol}': {e}",
			exc_info=True
		)

		raise HTTPException(status_code=500, detail="internal error")

# ───────────────────────────────────────────────────────────────────────────────
# ⏱️ Timed Watchdog for Graceful Profiling Shutdown
# ───────────────────────────────────────────────────────────────────────────────

async def watchdog_timer(timeout_sec: int) -> None:

	"""
		Waits for a given number of seconds,
		then triggers profiling shutdown.
	"""

	global EVENT_STREAM_ENABLE

	try:

		await asyncio.sleep(timeout_sec)

		logger.info(
			f"[watchdog_timer] {timeout_sec}s elapsed. "
			f"Initiating shutdown..."
		)

		EVENT_STREAM_ENABLE.clear()  # Signal downstream tasks to stop

		try:

			yappi.stop()				# Stop profiling

		except Exception as e:

			logger.error(
				f"[watchdog_timer] Failed to stop yappi: {e}",
				exc_info=True
			)

		try:

			dump_yappi_stats()		  # Dump profiler results to disk

		except Exception as e:

			logger.error(
				f"[watchdog_timer] Failed to dump yappi stats: {e}",
				exc_info=True
			)

		try:

			graceful_shutdown()		 # Close writers and background tasks

		except Exception as e:

			logger.error(
				f"[watchdog_timer] Failed to run graceful_shutdown: {e}",
				exc_info=True
			)

		logger.info("Profiling completed. Terminating application.")

		os._exit(0)					 # Force full process termination

	except Exception as e:

		logger.error(
			f"[watchdog_timer] Unexpected error: {e}",
			exc_info=True
		)

		os._exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 🧪 Start Profiling
# ───────────────────────────────────────────────────────────────────────────────

try:

	yappi.set_clock_type("wall")	# Walltime-based profiling
	yappi.start()

except Exception as e:

	logger.error(
		f"[profiling] Failed to start yappi profiler: {e}",
		exc_info=True
	)

# ───────────────────────────────────────────────────────────────────────────────
# 🧪 Result Dump on Exit
# ───────────────────────────────────────────────────────────────────────────────

def dump_yappi_stats() -> None:

	try:

		yappi.get_func_stats().save(
			"yappi_stats.callgrind", 
			type="callgrind"
		)

		logger.info("[profiling] Yappi stats dumped to yappi_stats.callgrind")

	except Exception as e:

		logger.error(
			f"[profiling] Failed to dump yappi stats: {e}",
			exc_info=True
		)

if PROFILE_DURATION > 0:

	atexit.register(dump_yappi_stats)   # Register dump on shutdown

# ───────────────────────────────────────────────────────────────────────────────
# 🚦 Main Entrypoint & Async Task Orchestration
# ───────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

	import asyncio
	from uvicorn.config import Config
	from uvicorn.server import Server

	async def main():

		try:

			# Initialize in-memory structures

			global READY_EVENT

			try:

				initialize_runtime_state()
				initialize_event_flags()
				assert_event_flags_initialized()

			except Exception as e:

				logger.error(
					f"[main] Initialization failed: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Launch background tasks
			# Handles periodic snapshot persistence per symbol

			try:

				for symbol in SYMBOLS:

					asyncio.create_task(dump_snapshot_for_symbol(symbol))

			except Exception as e:

				logger.error(
					f"[main] Failed to launch dump_snapshot_for_symbol tasks: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Streams and stores depth20@100ms `symbol_snapshots_to_render`

			try:

				asyncio.create_task(put_snapshot())

			except Exception as e:

				logger.error(
					f"[main] Failed to launch put_snapshot task: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Streams @depth for latency estimation

			try:

				asyncio.create_task(estimate_latency_via_diff_depth())

			except Exception as e:

				logger.error(
					f"[main] Failed to launch estimate_latency_via_diff_depth task: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Synchronize latency control

			try:

				asyncio.create_task(gate_streaming_by_latency())

			except Exception as e:

				logger.error(
					f"[main] Failed to launch gate_streaming_by_latency task: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Triggers shutdown after fixed duration (profiling scenario)

			if PROFILE_DURATION > 0:

				try:

					asyncio.create_task(
						watchdog_timer(timeout_sec=PROFILE_DURATION)
					)

					logger.info(
						"Profiling started. "
						f"Execution will stop after {PROFILE_DURATION} seconds."
					)

				except Exception as e:

					logger.error(
						f"[main] Failed to launch watchdog_timer: {e}",
						exc_info=True
					)

					sys.exit(1)

			# Wait for at least one valid snapshot before serving

			try:

				await READY_EVENT.wait()

			except Exception as e:

				logger.error(
					f"[main] Error while waiting for READY_EVENT: {e}",
					exc_info=True
				)

				sys.exit(1)

			# FastAPI

			try:

				logger.info(
					f"[main] FastAPI server starts. Try:\n"
					f"\thttp://localhost:8000/orderbook/{SYMBOLS[0]}\n"
				)

				cfg = Config(app=app, host="0.0.0.0", port=8000, lifespan="off", use_colors=False)
				server = Server(cfg)

				await server.serve()

			except Exception as e:

				logger.error(
					f"[main] FastAPI server failed to start: {e}",
					exc_info=True
				)

				sys.exit(1)

		except Exception as e:

			logger.critical(
				f"[main] Unhandled exception in main(): {e}",
				exc_info=True
			)

			sys.exit(1)

	try:

		asyncio.run(main())

	except KeyboardInterrupt:

		logger.info("[main] Application terminated by user (Ctrl + C).")
		sys.exit(0)

	except Exception as e:

		logger.critical(f"[main] Unhandled exception: {e}", exc_info=True)
		sys.exit(1)