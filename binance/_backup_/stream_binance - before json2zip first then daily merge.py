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
	Maintain top-20 in-memory `SYMBOL_SNAPSHOTS_TO_RENDER` for each symbol.
	Periodically persist `SYMBOL_SNAPSHOTS_TO_RENDER` to JSONL → zip → aggregate daily.
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
# Loads and parses the unified configuration file shared by both
# `stream_binance.py` and `get_binance_chart.py`.
#
# Defines all runtime parameters, including:
#   • SYMBOLS			→ Binance symbols to stream (e.g., BTCUSDT, ETHUSDT)
#   • SAVE_INTERVAL_MIN	→ File rotation interval (minutes) for snapshot persistence
#   • LOB_DIR			→ Output directory for JSONL and ZIP files
#   • BASE_BACKOFF,
# 	  MAX_BACKOFF, etc.	→ Retry/backoff strategy for reconnects
#   • MAX_WORKERS		→ Process pool size for daily merge operations
#   • DASHBOARD_STREAM_FREQ,
# 	  MAX_DASHBOARD_CONNECTIONS,
# 	  etc.				→ WebSocket dashboard limits
#
# 📄 Filename: get_binance_chart.conf
# Format: Plaintext `KEY=VALUE`, supporting inline `#` comments.
#
# ⚠️ IMPORTANT:
#   - Always loaded via `resource_path()` for compatibility with both
#	 development (Windows) and production (PyInstaller/Linux) environments.
#   - When bundled with PyInstaller, the config is extracted to a temp folder
#	 at runtime (e.g., `/tmp/_MEIxxxx`), resolved via `sys._MEIPASS`.
#
# 🛠️ Robustness Notes:
#   - Loader expects the config file to be present and well-formed.
#   - If missing or malformed, the application logs an error and exits.
#   - SYMBOLS=None or missing triggers a fatal runtime error.
#   - All configuration is centralized here for maintainability and clarity.
#
# See also:
#   - RULESET.md for documentation and code conventions.
#   - All config-driven parameters are referenced throughout the codebase.
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

	global CONFIG

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

STREAMS_PARAM = "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL		  = f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

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
# Structures:
#   • LATENCY_DICT: Tracks recent latency samples per symbol (rolling deque).
#   • MEDIAN_LATENCY_DICT: Stores median latency (ms) per symbol, updated dynamically.
#   • DEPTH_UPDATE_ID_DICT: Records the latest `updateId` for each symbol to ensure
#	 proper sequencing of depth updates.
#
# Usage:
#   - LATENCY_DICT: Used for latency estimation and validation.
#   - MEDIAN_LATENCY_DICT: Provides latency compensation for timestamp adjustments.
#   - DEPTH_UPDATE_ID_DICT: Prevents out-of-order updates from being processed.
# ───────────────────────────────────────────────────────────────────────────────

LATENCY_DICT:		   Dict[str, Deque[float]] = {}
MEDIAN_LATENCY_DICT:   Dict[str, float] = {}
DEPTH_UPDATE_ID_DICT:  Dict[str, int] = {}

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
	MAX_BACKOFF			= int(CONFIG.get("MAX_BACKOFF", 30))
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
# ───────────────────────────────────────────────────────────────────────────────
# Maintains all per-symbol runtime state required for streaming, persistence,
# API rendering, and safe daily merge orchestration.
#
# Responsibilities:
#   • Snapshot ingestion (async queue per symbol, for file persistence)
#   • API rendering (in-memory latest snapshot for FastAPI endpoints)
#   • File writing (active file handle per symbol, rotated by time window)
#   • Daily merge deduplication (tracks merged days per symbol)
#   • Thread/process safety for merge triggers (per-symbol locks)
#
# Structures:
#
#   SNAPSHOTS_QUEUE_DICT: dict[str, asyncio.Queue[dict]]
#	 → Per-symbol async queues for order book snapshots.
#	   Populated by `put_snapshot()`, consumed by `symbol_dump_snapshot()`.
#
#   SYMBOL_SNAPSHOTS_TO_RENDER: dict[str, dict]
#	 → In-memory latest snapshot per symbol for FastAPI rendering.
#	   Used for diagnostics/UI only; not persisted to disk.
#
#   SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]]
#	 → Tracks open file writers per symbol:
#		└── (last_suffix, writer) where:
#			• last_suffix: str = time suffix like "2025-07-03_15-00"
#			• writer: open text file handle for appending .jsonl data
#
#   MERGED_DAYS: dict[str, set[str]]
#	 → For each symbol, contains UTC day strings ("YYYY-MM-DD") that have
#	   already been merged and archived, preventing redundant merge triggers.
#
#   MERGE_LOCKS: dict[str, threading.Lock]
#	 → Per-symbol locks to prevent race conditions on `MERGED_DAYS` and
#	   ensure only one merge process is launched per symbol/day.
#
# Notes:
#   - All structures are (re-)initialized via `initialize_runtime_state()`.
#   - Thread/process safety is enforced for all merge-related state.
#   - See also: RULESET.md for code conventions and documentation standards.
# ───────────────────────────────────────────────────────────────────────────────

SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}
SYMBOL_SNAPSHOTS_TO_RENDER: dict[str, dict] = {}
SYMBOL_TO_FILE_HANDLES:		dict[str, tuple[str, TextIOWrapper]] = {}

# Each symbol has its own threading.Lock to ensure
# independent synchronization during merge operations.

MERGED_DAYS: dict[str, set[str]] = {}
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

		SYMBOL_SNAPSHOTS_TO_RENDER.clear()
		SYMBOL_SNAPSHOTS_TO_RENDER.update({
			symbol: {}
			for symbol in SYMBOLS
		})

		SYMBOL_TO_FILE_HANDLES.clear()
		MERGED_DAYS.clear()
		MERGED_DAYS.update({
			symbol: set() for symbol in SYMBOLS
		})

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
#   • symbol_consolidate_a_day(...)
# 	  → Merges minute-level .zip files a daily archive
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

# ───────────────────────────────────────────────────────────────────────────────
# 🗃️ Per-Symbol Daily Snapshot Consolidation & Archival
#
# Merges all per-minute zipped order book snapshots for a given symbol and UTC day
# into a single `.jsonl` file, then compresses it as a daily archive.
#
# Responsibilities:
#   • Locate all `.zip` files for the symbol/day in the temp directory.
#   • Unpack and concatenate their contents into a single `.jsonl` file.
#   • Compress the consolidated `.jsonl` as a single daily `.zip` archive.
#   • Optionally purge the original temp directory after archiving.
#
# Fault Tolerance:
#   - Gracefully skips missing/corrupted files or directories.
#   - Logs all errors; never throws to caller.
#
# Usage:
#   - Called via process pool for each symbol/day rollover.
#   - Ensures efficient long-term storage and fast downstream loading.
#
# See also:
#   - symbol_trigger_merge(), symbol_dump_snapshot()
#   - RULESET.md for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

def symbol_consolidate_a_day(
	symbol:	  str,
	day_str:  str,
	base_dir: str,
	purge:	  bool = True
):

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

		logger.error(
			f"[merge_day_zips][{symbol}] "
			f"Temp dir missing on {day_str}: {tmp_dir}"
		)

		return

	# List all zipped minute-level files (may be empty)

	try:

		zip_files = [f for f in os.listdir(tmp_dir) if f.endswith(".zip")]

	except Exception as e:

		logger.error(
			f"[merge_day_zips][{symbol}] "
			f"Failed to list zips in {tmp_dir}: {e}",
			exc_info=True
		)

		return

	if not zip_files:

		logger.error(
			f"[merge_day_zips][{symbol}] "
			f"No zip files to merge on {day_str}."
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
							f"[merge_day_zips][{symbol}] "
							f"Failed to extract {zip_path}: {e}",
							exc_info=True
						)

						return

		except Exception as e:

			logger.error(
				f"[merge_day_zips][{symbol}] "
				f"Failed to open or write to merged file {merged_path}: {e}",
				exc_info=True

			)

			try:

				if fout: fout.close()

			except Exception as close_error:
				
				logger.error(
					f"[merge_day_zips][{symbol}] "
					f"Failed to close output file: {close_error}",
					exc_info=True
				)

			return

		finally:

			# Ensure the output file is closed

			try:

				if fout: fout.close()

			except Exception as close_error:

				logger.error(
					f"[merge_day_zips][{symbol}] "
					f"Failed to close output file: {close_error}",
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
				f"[merge_day_zips][{symbol}] "
				f"Failed to compress merged file on {day_str}: {e}",
				exc_info=True
			)

			# Do not remove .jsonl if compression failed

			return

		# Remove intermediate plain-text .jsonl file after compression

		try:

			if os.path.exists(merged_path):

				os.remove(merged_path)

		except Exception as e:

			logger.error(
				f"[merge_day_zips][{symbol}] "
				f"Failed to remove merged .jsonl on {day_str}: {e}",
				exc_info=True
			)

		# Optionally delete the original temp folder containing per-minute zips

		if purge:

			try:

				shutil.rmtree(tmp_dir)

			except Exception as e:

				logger.error(
					f"[merge_day_zips][{symbol}] "
					f"Failed to remove temp dir {tmp_dir}: {e}",
					exc_info=True
				)

	except FileNotFoundError as e:

		logger.error(
			f"[merge_day_zips][{symbol}] "
			f"No files found to merge on {day_str}: {e}"
		)

		return

	except Exception as e:

		logger.error(
			f"[merge_day_zips][{symbol}] "
			f"Unexpected error merging on {day_str}: {e}",
			exc_info=True
		)

		return

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

async def estimate_latency() -> None:

	"""
	🔁 Latency Estimator via Binance @depth Stream

	This coroutine connects to the Binance `@depth` WebSocket stream 
	(not `@depth20@100ms`) to measure **effective downstream latency**
	for each tracked symbol.

	Latency is estimated by comparing:
		latency ≈ client_time_sec - server_time_sec

	Where:
	- `server_time_sec` is the server-side event timestamp ("E").
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
					f"[estimate_latency] "
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

						if ((update_id is None) or
							(update_id <= DEPTH_UPDATE_ID_DICT.get(symbol, 0))
						):

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
										"[estimate_latency] "
										f"Latency OK — all symbols within threshold. "
										f"Event set."
									)
					except Exception as e:

						logger.warning(
							f"[estimate_latency] "
							f"Failed to process message: {e}",
							exc_info=True
						)

						continue

		except Exception as e:

			reconnect_attempt += 1

			logger.warning(
				f"[estimate_latency] "
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
				f"[estimate_latency] "
				f"Retrying in {backoff_sec:.1f} seconds "
				f"(attempt {reconnect_attempt})..."
			)

			await asyncio.sleep(backoff_sec)

		finally:

			logger.info(
				f"[estimate_latency] "
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
#
# Consumes Binance `@depth20@100ms` WebSocket snapshots for all tracked symbols,
# applies latency compensation, and dispatches each processed snapshot to:
#   • SNAPSHOTS_QUEUE_DICT[symbol] — for persistent file logging
#   • SYMBOL_SNAPSHOTS_TO_RENDER[symbol] — for live debug rendering via FastAPI
#
# Responsibilities:
#   • Waits for EVENT_STREAM_ENABLE to confirm latency quality
#   • For each stream message:
#	   - Extracts symbol, bid/ask levels, and last update ID
#	   - Applies median-latency correction to compute eventTime (ms)
#	   - Dispatches snapshot to both persistence queue and render cache
#
# Notes:
#   - Binance partial streams like @depth20@100ms lack server-side timestamps ("E");
#	 all timing is client-side and latency-compensated
#   - eventTime is an int (milliseconds since UNIX epoch)
#   - Only SNAPSHOTS_QUEUE_DICT[symbol] is used for durable storage
#   - SYMBOL_SNAPSHOTS_TO_RENDER is ephemeral, used for diagnostics or FastAPI display
#   - On failure, reconnects with exponential backoff and jitter
# ───────────────────────────────────────────────────────────────────────────────

async def put_snapshot() -> None:

	global SNAPSHOTS_QUEUE_DICT
	global LATENCY_DICT, MEDIAN_LATENCY_DICT, SHARED_STATE_DICT

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

						SYMBOL_SNAPSHOTS_TO_RENDER[symbol] = snapshot

						# 🔓 Signal FastAPI readiness after first snapshot

						if not READY_EVENT.is_set():

							READY_EVENT.set()

					except Exception as e:

						logger.warning(
							f"[put_snapshot][{symbol}] "
							f"Failed to process message: {e}",
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
# 📝 Background Task: Snapshot Persistence & Daily Merge Trigger
#
# Handles per-symbol snapshot persistence and triggers daily merge/archival.
#
# Responsibilities:
#   • Consumes snapshots from `SNAPSHOTS_QUEUE_DICT[symbol]` and appends them
#	 to per-symbol `.jsonl` files, partitioned by time window.
#   • Rotates file handles when the time window (suffix) changes.
#   • On UTC day rollover, triggers a merge/archival process for the previous day,
#	 ensuring only one merge per symbol/day via `MERGED_DAYS` and `MERGE_LOCKS`.
#
# Structures:
#   • `SYMBOL_TO_FILE_HANDLES[symbol]` — Tracks (suffix, writer) for each symbol.
#   • `MERGED_DAYS[symbol]` — Set of merged days to prevent redundant merges.
#   • `MERGE_LOCKS[symbol]` — Thread/process lock for safe merge triggering.
#
# Notes:
#   - Runs as an infinite async task per symbol.
#   - Ensures all data is flushed to disk after each snapshot.
#   - Merge/archival is dispatched only once per UTC day per symbol.
#   - See also: RULESET.md for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

def symbol_trigger_merge(symbol, last_day):

	global MERGE_EXECUTOR, LOB_DIR, PURGE_ON_DATE_CHANGE

	MERGE_EXECUTOR.submit(
		symbol_consolidate_a_day,
		symbol,
		last_day,
		LOB_DIR,
		PURGE_ON_DATE_CHANGE == 1
	)

async def symbol_dump_snapshot(symbol: str) -> None:

	global SYMBOL_TO_FILE_HANDLES, SNAPSHOTS_QUEUE_DICT
	global EVENT_STREAM_ENABLE

	queue = SNAPSHOTS_QUEUE_DICT[symbol]

	while True:

		# Block until new snapshot is received

		try:

			snapshot = await queue.get()

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"❌ Failed to get snapshot from queue: {e}",
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
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"❌ Failed to compute suffix/day: {e}",
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
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"❌ Failed to build file path: {e}",
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
					# merge operations. `MERGED_DAYS[symbol].add(last_day)`
					# and `threading.Thread(...)` calls are guaranteed
					# to execute only once per symbol and day combination.
					# Even if `symbol_consolidate_a_day` fails, 
					# the state in `MERGED_DAYS[symbol]` prevents redundant
					# merge attempts for the same day.
					# .....................................................

					if ((last_day != day_str) and 
						(last_day not in MERGED_DAYS[symbol])
					):

						MERGED_DAYS[symbol].add(last_day)
						
						symbol_trigger_merge(symbol, last_day)

		except Exception as e:

			logger.warning(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"❌ Failed to spawn merge thread: {e}",
				exc_info=True
			)

		# ── Rotate writer if suffix (HHMM) window has changed

		if last_suffix != suffix:

			if writer:

				try:

					writer.close()

				except Exception as e:

					logger.warning(
						f"[symbol_dump_snapshot][{symbol.upper()}] "
						f"❌ Close failed → {e}",
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
						f"[symbol_dump_snapshot][{symbol.upper()}] "
						f"❌ zip_and_remove failed: {e}",
						exc_info=True
					)

			try:

				writer = open(file_path, "a", encoding="utf-8")

			except OSError as e:

				logger.error(
					f"[symbol_dump_snapshot][{symbol.upper()}] "
					f"❌ Open failed: {file_path} → {e}",
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
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"❌ Write failed: {file_path} → {e}",
				exc_info=True
			)

			# Invalidate writer for next iteration

			SYMBOL_TO_FILE_HANDLES.pop(symbol, None)

			continue

# ───────────────────────────────────────────────────────────────────────────────
# 🛑 Graceful Shutdown Handlers (FastAPI Lifespan & Merge Executor)
#
# Ensures all background merge processes and file writers are safely closed
# and all data is flushed to disk on application shutdown.
#
# Responsibilities:
#   • Registers an atexit handler to gracefully shutdown the ProcessPoolExecutor,
#	 waiting for all merge tasks to complete.
#   • Implements FastAPI lifespan context to close all open file writers for
#	 each symbol, guaranteeing no snapshot data loss on exit.
#
# Notes:
#   - Replaces deprecated @APP.on_event("shutdown") with modern lifespan context.
#   - Guarantees data integrity and resource cleanup across all shutdown scenarios.
#   - See also: RULESET.md for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

import atexit

def shutdown_merge_executor():

	global MERGE_EXECUTOR

	try:

		MERGE_EXECUTOR.shutdown(wait=True)

		logger.info(
			f"[main] MERGE_EXECUTOR shutdown safely complete."
		)

	except Exception as e:

		logger.error(
			f"[main] MERGE_EXECUTOR shutdown failed: {e}",
			exc_info=True
		)

atexit.register(shutdown_merge_executor)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(APP):

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
# ⚙️ FastAPI Initialization & Template Binding
#
# FastAPI acts as the core runtime backbone for this application.
# Its presence is structurally required for multiple critical subsystems:
#
#   1. 📊 Logging Integration:
#	  - Logging is routed via `uvicorn.error`, managed by FastAPI's ASGI server.
#	  - Our logger (`logger = logging.getLogger("uvicorn.error")`) is active
#		and functional as soon as FastAPI is imported, even before APP launch.
#
#   2. 🌐 REST API Endpoints:
#	  - Provides health checks, JSON-based order book access, and real-time UI rendering.
#
#   3. 🧱 HTML UI Layer:
#	  - Jinja2 template system is integrated via FastAPI for `/orderbook/{symbol}`.
#
# ⚠️ Removal of FastAPI would break:
#	  - Logging infrastructure
#	  - REST endpoints (/health, /state)
#	  - HTML visualization
#
#   - Even if not all FastAPI features are always used, its presence is mandatory.
#   - Template directory is resolved via `resource_path()` for PyInstaller compatibility.
#   - See also: RULESET.md for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

APP = FastAPI(lifespan=lifespan)

# ───────────────────────────────────────────────────────────────────────────────
# 🔍 Healthcheck Endpoints
# ───────────────────────────────────────────────────────────────────────────────

@APP.get("/health/live")
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

@APP.get("/health/ready")
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

@APP.get("/state/{symbol}")
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

		if symbol not in SYMBOL_SNAPSHOTS_TO_RENDER:

			raise HTTPException(status_code=404, detail="symbol not found")

		return JSONResponse(content=SYMBOL_SNAPSHOTS_TO_RENDER[symbol])

	except Exception as e:

		logger.error(
			f"[get_order_book] Failed to serve order book for '{symbol}': {e}",
			exc_info=True
		)
		
		raise HTTPException(status_code=500, detail="internal error")

# ───────────────────────────────────────────────────────────────────────────────
# 👁️ HTML UI for Order Book
# ───────────────────────────────────────────────────────────────────────────────

@APP.get("/orderbook/{symbol}", response_class=HTMLResponse)
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

		if sym not in SYMBOL_SNAPSHOTS_TO_RENDER:

			raise HTTPException(status_code=404, detail="symbol not found")

		data = SYMBOL_SNAPSHOTS_TO_RENDER[sym]
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
# 📊 Dashboard WebSocket Stream Handler
#
# Streams real-time monitoring data (e.g., median latency per symbol)
# to connected dashboard clients via WebSocket.
#
# Features:
#   • Accepts WebSocket connections at `/ws/dashboard` (endpoint is extensible).
#   • Enforces a global concurrent connection limit (`MAX_DASHBOARD_CONNECTIONS`)
#	 with thread-safe tracking and immediate refusal of excess clients.
#   • Each session is limited to `MAX_DASHBOARD_SESSION_SEC` seconds (from .conf),
#	 after which the connection is closed gracefully.
#   • Periodically sends a JSON object containing per-symbol median latency.
#   • Robust to disconnects, task cancellations, and transient errors.
#   • Implements exponential backoff (from .conf) for repeated connection failures.
#   • All resource management (locks, counters) is handled with minimal overhead.
#
# Usage:
#   - Designed for extensibility: add more metrics (CPU, memory, etc.) as needed.
#   - Intended for use with a browser-based dashboard or monitoring tool.
#
# Safety & Robustness:
#   - Never throws uncaught exceptions; all errors are logged.
#   - Ensures the server remains robust even under repeated client connect/disconnect.
#   - Resource usage is minimal when idle; handler is always alive.
#   - All configuration (limits, intervals, backoff) is loaded from `.conf`.
#
# See also:
#   - `DASHBOARD_STREAM_FREQ`, `MAX_DASHBOARD_CONNECTIONS`, `MAX_DASHBOARD_SESSION_SEC`
#   - Project style: see `RULESET.md` for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

from fastapi import WebSocket, WebSocketDisconnect

DASHBOARD_STREAM_FREQ		 = float(CONFIG.get("DASHBOARD_STREAM_FREQ", 0.03))
MAX_DASHBOARD_CONNECTIONS	 = int(CONFIG.get("MAX_DASHBOARD_CONNECTIONS", 3))
MAX_SESSION_SECONDS			 = int(CONFIG.get("MAX_DASHBOARD_SESSION_SEC", 600))

ACTIVE_DASHBOARD_LOCK		 = asyncio.Lock()
ACTIVE_DASHBOARD_CONNECTIONS = 0

@APP.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):

	"""
	Streams dashboard monitoring data (e.g., med_latency) to WebSocket clients.

	On disconnect or error, logs and waits before allowing reconnection.
	Designed for extensibility: add more metrics as needed.
	"""

	global SYMBOLS, MEDIAN_LATENCY_DICT
	global DASHBOARD_STREAM_FREQ, MAX_DASHBOARD_CONNECTIONS
	global ACTIVE_DASHBOARD_CONNECTIONS, ACTIVE_DASHBOARD_LOCK

	reconnect_attempt = 0  # Track consecutive accept failures for backoff

	while True:

		try:

			# ── Limit concurrent dashboard connections

			async with ACTIVE_DASHBOARD_LOCK:

				if ACTIVE_DASHBOARD_CONNECTIONS >= MAX_DASHBOARD_CONNECTIONS:

					await websocket.close(
						code = 1008,
						reason = "Too many dashboard clients connected."
					)

					logger.warning(
						"[websocket_dashboard] "
						"Connection refused: too many clients."
					)
					return

				ACTIVE_DASHBOARD_CONNECTIONS += 1

			try:

				# Attempt to accept a new WebSocket connection from a dashboard client

				await websocket.accept()
				reconnect_attempt = 0		# Reset backoff on successful accept

				# Track session start time for session timeout
				import time
				start_time = time.time()

				# Main data push loop: send metrics until client disconnects, 
				# error, or session timeout

				while True:

					try:
						# Construct the monitoring payload (add more fields as needed)

						data = {
							"med_latency": {
								symbol: int(MEDIAN_LATENCY_DICT.get(symbol, 0.0))
								for symbol in SYMBOLS
							}
						}

						# Send the JSON payload to the connected client

						await websocket.send_json(data)

						# Check session duration and close if exceeded

						if time.time() - start_time > MAX_SESSION_SECONDS:
							await websocket.close(
								code=1000, reason="Session time limit reached."
							)
							logger.info(
								f"[websocket_dashboard] "
								f"Session time limit reached, connection closed."
							)
							break

						# Wait for the configured interval before sending the next update

						await asyncio.sleep(DASHBOARD_STREAM_FREQ)

					except WebSocketDisconnect:

						# Client closed the connection (normal case)

						logger.info(
							f"[websocket_dashboard] "
							f"WebSocket client disconnected."
						)
						break

					except asyncio.CancelledError:

						# Task was cancelled (e.g., server shutdown)

						logger.info(
							f"[websocket_dashboard] "
							f"WebSocket handler task cancelled."
						)
						break

					except Exception as e:

						# Log unexpected errors, then break to allow reconnection

						logger.warning(
							f"[websocket_dashboard] WebSocket error: {e}",
							exc_info=True
						)
						break

				# Exit inner loop: client disconnected, error, or session timeout
				# Outer loop allows for reconnection attempts if desired

				break  # Remove this break to allow the same client to reconnect in-place

			finally:

				# ── Decrement connection count on disconnect or error

				async with ACTIVE_DASHBOARD_LOCK:
					ACTIVE_DASHBOARD_CONNECTIONS -= 1

		except Exception as e:

			# Accept failed (e.g., handshake error, resource exhaustion)

			reconnect_attempt += 1
			logger.warning(
				f"[websocket_dashboard] "
				f"Accept failed (attempt {reconnect_attempt}): {e}",
				exc_info=True
			)

			# Exponential backoff with jitter to avoid tight reconnect loops

			backoff = min(
				MAX_BACKOFF, BASE_BACKOFF * (2 ** reconnect_attempt)
			) + random.uniform(0, 1)

			if reconnect_attempt > RESET_CYCLE_AFTER:
				reconnect_attempt = RESET_BACKOFF_LEVEL

			logger.info(
				f"[websocket_dashboard] "
				f"Retrying accept in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

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

	from uvicorn.config import Config
	from uvicorn.server import Server
	from concurrent.futures import ProcessPoolExecutor
	import asyncio

	# Use ProcessPoolExecutor for process-based parallelism to minimize GIL impact.

	MAX_WORKERS	   = int(CONFIG.get("MAX_WORKERS", 8))
	MERGE_EXECUTOR = ProcessPoolExecutor(max_workers=MAX_WORKERS)

	# ───────────────────────────────────────────────────────────────────────────

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

					asyncio.create_task(symbol_dump_snapshot(symbol))

			except Exception as e:

				logger.error(
					f"[main] Failed to launch symbol_dump_snapshot tasks: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Streams and stores depth20@100ms `SYMBOL_SNAPSHOTS_TO_RENDER`

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

				asyncio.create_task(estimate_latency())

			except Exception as e:

				logger.error(
					f"[main] Failed to launch estimate_latency task: {e}",
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

				cfg = Config(
					app			= APP,
					host		= "0.0.0.0",
					port		= 8000,
					lifespan	= "off",
					use_colors	= False
				)

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
		
	except Exception as e:

		logger.critical(f"[main] Unhandled exception: {e}", exc_info=True)
		sys.exit(1)

	finally:
		
		pass
