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
	python==3.9.23
	pyinstaller==6.14.2
	pyinstaller==hooks-contrib-2025.5
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	psutil==7.0.0
	memray==1.17.2
	pyflowchart==0.3.1

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

import inspect

from stream_binance_globals import (
	my_name,		# For `Exception` that almost-surely does not happen.
	resource_path,
	load_config,
)

import asyncio, threading, time, random
from datetime import datetime, timezone
import sys, os, certifi, shutil, zipfile
import json, statistics
from collections import deque
from io import TextIOWrapper
from typing import Optional
from collections import OrderedDict

os.environ["SSL_CERT_FILE"] = certifi.where()

# ───────────────────────────────────────────────────────────────────────────────
# 📝 Logging Configuration: Rotating log file + console output with UTC timestamps
# ───────────────────────────────────────────────────────────────────────────────

import logging
from logging.handlers import RotatingFileHandler

# ───────────────────────────────────────────────────────────────────────────────
# 🕔 Global Time Utilities
# ───────────────────────────────────────────────────────────────────────────────

def get_current_time_ms() -> int:

	"""
	Returns the current time in milliseconds as an integer.
	Uses nanosecond precision for maximum accuracy.
	"""

	return time.time_ns() // 1_000_000

def ms_to_datetime(ms: int) -> datetime:

	"""
	Converts a millisecond timestamp to a UTC datetime object.
	"""

	return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

class NanoTimer:

	"""
	A class for high-precision timing using nanoseconds.
	Provides methods to record a start time (tick) and calculate
	the elapsed time in seconds (tock).
	"""

	def __init__(self, reset_on_instantiation: bool = True):

		self.start_time_ns = (
			time.time_ns() if reset_on_instantiation else None
		)

	def tick(self):
		
		self.start_time_ns = time.time_ns()

	def tock(self) -> float:

		"""
		Calculates the elapsed time in seconds since the last tick.

		Returns:
			float: Elapsed time in seconds.
		Raises:
			ValueError: If tick() has not been called before tock().
		"""

		if self.start_time_ns is None:

			raise ValueError("tick() must be called before tock().")

		elapsed_ns = time.time_ns() - self.start_time_ns

		return elapsed_ns / 1_000_000_000.0

	def __enter__(self):

		self.tick()

		return self

	def __exit__(self, exc_type, exc_value, traceback):

		pass

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
		return dt.isoformat(timespec='microseconds')

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
# Unified Logger for FastAPI, Uvicorn, websockets, and all dependencies.
# All logs are routed to both file and console with UTC timestamps.
# ───────────────────────────────────────────────────────────────────────────────

try:

	# ───────────────────────────────────────────────────────────────────────────
	# Root logger: attach file and console handlers
	# ───────────────────────────────────────────────────────────────────────────
	
	logger = logging.getLogger()
	
	logger.addHandler(
		RotatingFileHandler(
			"stream_binance.log",
			maxBytes	= 10_000_000,	# Rotate after 10 MB
			backupCount	= 100			# Keep # of backups
		)
	)
	
	logger.addHandler(
		logging.StreamHandler()
	)
	
	logger.setLevel(logging.INFO)		# Default: INFO

	# ───────────────────────────────────────────────────────────────────────────
	# Uvicorn & FastAPI: WARNING
	# ───────────────────────────────────────────────────────────────────────────

	for name in [
		"fastapi", "uvicorn",
		"uvicorn.error",
		"uvicorn.access"
	]:
		
		specific_logger = logging.getLogger(name)
		specific_logger.setLevel(logging.WARNING)
		specific_logger.propagate = True

	# ───────────────────────────────────────────────────────────────────────────
	# All Others: INFO
	# ───────────────────────────────────────────────────────────────────────────

	for name in [
		"websockets",
		"websockets.server",
		"websockets.client",
		"starlette",
		"asyncio",
		"concurrent.futures"
	]:
		individual_logger = logging.getLogger(name)
		individual_logger.setLevel(logging.INFO)
		individual_logger.propagate = True

	formatter = UTCFormatter(
		f"[%(asctime)s] "
		f"%(levelname)s: "
		f"%(message)s"
	)
	
	for handler in logger.handlers:
		handler.setFormatter(formatter)

except Exception as e:

	print(
		f"[{datetime.now(timezone.utc).isoformat()}] "
		f"ERROR: [global] Failed to "
		f"initialize logging: {e}",
		file=sys.stderr
	)

	sys.exit(1)


# ───────────────────────────────────────────────────────────────────────────────
# 📦 Third-Party Dependencies (from requirements.txt)
# ───────────────────────────────────────────────────────────────────────────────

import websockets
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

try:

	CONFIG, SYMBOLS, WS_URL = load_config(logger)

except Exception as e:

	logger.critical(
		f"[load_config] Failed to load config: {e}"
		f"Application cannot start.",
		exc_info=True
	)

	exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 📈 Latency Measurement Parameters
# These control how latency is estimated from the @depth stream:
#   - LATENCY_DEQUE_SIZE:	 buffer size for per-symbol latency samples
#   - LATENCY_SAMPLE_MIN:	 number of samples required before validation
#   - LATENCY_THRESHOLD_MS:  max latency allowed for stream readiness
#   - ASYNC_SLEEP_INTERVAL:  Seconds to sleep in asyncio tasks
# ───────────────────────────────────────────────────────────────────────────────

LATENCY_DEQUE_SIZE   = int(CONFIG.get("LATENCY_DEQUE_SIZE",		10))
LATENCY_SAMPLE_MIN   = int(CONFIG.get("LATENCY_SAMPLE_MIN",		10))
LATENCY_THRESHOLD_MS = int(CONFIG.get("LATENCY_THRESHOLD_MS",	500))
LATENCY_SIGNAL_SLEEP = float(CONFIG.get("LATENCY_SIGNAL_SLEEP", 0.2))
LATENCY_GATE_SLEEP	 = float(CONFIG.get("LATENCY_GATE_SLEEP", 0.2))
ASYNC_SLEEP_INTERVAL = float(CONFIG.get("LATENCY_GATE_SLEEP",	1.0))

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
# ───────────────────────────────────────────────────────────────────────────────

LATENCY_DICT:		  dict[str, deque[int]] = {}
MEDIAN_LATENCY_DICT:  dict[str, int] = {}
DEPTH_UPDATE_ID_DICT: dict[str, int] = {}

LATEST_JSON_FLUSH:	  dict[str, int] = {}
JSON_FLUSH_INTERVAL:  dict[str, int] = {}

# ───────────────────────────────────────────────────────────────────────────────
# 🔒 Global Event Flags (pre-declared to prevent NameError)
# - Properly initialized inside `main()` to bind to the right loop
# - ✅ Minimalistic pattern for single-instance runtime
# - ⚠️ Consider `AppContext` encapsulation
# 	if modularization/multi-instance is needed
# ───────────────────────────────────────────────────────────────────────────────

EVENT_1ST_SNAPSHOT:	 asyncio.Event
EVENT_LATENCY_VALID: asyncio.Event
EVENT_STREAM_ENABLE: asyncio.Event

EVENT_FLAGS_INITIALIZED = False

def initialize_event_flags():

	"""
	Initializes global asyncio.Event flags for controlling stream state.
	Logs any exception and terminates if initialization fails.
	"""

	try:

		global EVENT_1ST_SNAPSHOT, EVENT_LATENCY_VALID, EVENT_STREAM_ENABLE
		global EVENT_FLAGS_INITIALIZED

		EVENT_1ST_SNAPSHOT = asyncio.Event()
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
# 📦 Runtime Memory Buffers & Async File Handles
# ───────────────────────────────────────────────────────────────────────────────

SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES:		dict[str, tuple[str, TextIOWrapper]] = {}

SNAPSHOTS_QUEUE_MAX = int(CONFIG.get("SNAPSHOTS_QUEUE_MAX",	100))

RECORDS_MERGED_DATES: dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:  dict[str, OrderedDict[str]] = {}	# ZNR := zip_n_remove
RECORDS_MAX = int(CONFIG.get("RECORDS_MAX", 10))

# ───────────────────────────────────────────────────────────────────────────────

def initialize_runtime_state():

	try:
		global SYMBOLS
		global LATENCY_DICT, MEDIAN_LATENCY_DICT, DEPTH_UPDATE_ID_DICT
		global LATEST_JSON_FLUSH, JSON_FLUSH_INTERVAL
		global SNAPSHOTS_QUEUE_DICT, SNAPSHOTS_QUEUE_MAX

		LATENCY_DICT.clear()
		LATENCY_DICT.update({
			symbol: deque(maxlen=LATENCY_DEQUE_SIZE)
			for symbol in SYMBOLS
		})

		MEDIAN_LATENCY_DICT.clear()
		MEDIAN_LATENCY_DICT.update({
			symbol: 0
			for symbol in SYMBOLS
		})

		DEPTH_UPDATE_ID_DICT.clear()
		DEPTH_UPDATE_ID_DICT.update({
			symbol: 0
			for symbol in SYMBOLS
		})

		LATEST_JSON_FLUSH.clear()
		LATEST_JSON_FLUSH.update({
			symbol: get_current_time_ms()
			for symbol in SYMBOLS
		})

		JSON_FLUSH_INTERVAL.clear()
		JSON_FLUSH_INTERVAL.update({
			symbol: 0
			for symbol in SYMBOLS
		})

		# ───────────────────────────────────────────────────────────────────────

		SNAPSHOTS_QUEUE_DICT.clear()
		SNAPSHOTS_QUEUE_DICT.update({
			symbol: asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
			for symbol in SYMBOLS
		})

		SYMBOL_TO_FILE_HANDLES.clear()

		RECORDS_MERGED_DATES.clear()
		RECORDS_MERGED_DATES.update({
			symbol: OrderedDict()
			for symbol in SYMBOLS
		})

		RECORDS_ZNR_MINUTES.clear()
		RECORDS_ZNR_MINUTES.update({
			symbol: OrderedDict()
			for symbol in SYMBOLS
		})

		logger.info(
			f"[initialize_runtime_state] "
			f"Runtime state initialized."
		)

	except Exception as e:

		logger.error(
			"[initialize_runtime_state] "
			f"Failed to initialize runtime state: {e}",
			exc_info=True
		)
		sys.exit(1)

# ───────────────────────────────────────────────────────────────────────────────
# 🕓 Latency Control: Measurement, Thresholding, and Flow Gate
# ───────────────────────────────────────────────────────────────────────────────

async def gate_streaming_by_latency() -> None:

	"""
	Streaming controller based on latency.
	Manages `EVENT_STREAM_ENABLE` flag for order book streaming.
	Observes `EVENT_LATENCY_VALID`, set by latency estimation loop.
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
					f"Enable order book stream.\n"
				)

				EVENT_STREAM_ENABLE.set()
				has_logged_warmup = False

			elif not latency_passed:

				if not has_any_latency and not has_logged_warmup:

					logger.info(
						f"[gate_streaming_by_latency] "
						f"Warming up latency measurements...\n"
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

# ───────────────────────────────────────────────────────────────────────────────

async def estimate_latency() -> None:

	"""
	🔁 Latency Estimator via Binance @depth Stream

	This coroutine connects to the Binance @depth WebSocket stream 
	(not @depth20@100ms) to measure effective downstream latency 
	for each tracked symbol.

	Latency is estimated by comparing:
		latency ≈ get_current_time_ms() - server_time_ms

	Where:
	- server_time_ms is the server-side event timestamp ("E").
	- get_current_time_ms() is the actual receipt time on the local machine.

	🕒 This difference reflects:
		• Network propagation delay
		• OS-level socket queuing
		• Python event loop scheduling
	and thus represents a realistic approximation of one-way latency.

	Behavior:
	- Maintains a rolling deque of latency samples per symbol.
	- Once LATENCY_SAMPLE_MIN samples exist:
		• Computes median latency per symbol.
		• If all medians < LATENCY_THRESHOLD_MS, sets EVENT_LATENCY_VALID.
		• If excessive latency or disconnection, clears the signal.

	🎯 Purpose:
	- EVENT_LATENCY_VALID acts as a global flow control flag.
	- Used by gate_streaming_by_latency() to pause/resume 
	order book streaming via EVENT_STREAM_ENABLE.

	🔄 Backoff:
	- On disconnection or failure, retries with exponential backoff and jitter.

	📌 Notes:
	- This is not a true RTT (round-trip time) estimate.
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
						server_time_ms = data.get("E")

						if server_time_ms is None:

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
					
						# ─────────────────────────────────────────────────────────────────
						# Estimate latency (difference between client and server clocks)
						# ─────────────────────────────────────────────────────────────────
						# `get_current_time_ms() - server_time_ms` approximates one-way
						# latency (network + kernel + event loop) at the point of message
						# receipt. While not a true RTT, it reflects realistic downstream
						# delay and is sufficient for latency gating decisions in practice.
						# ─────────────────────────────────────────────────────────────────

						latency_ms = get_current_time_ms() - server_time_ms

						LATENCY_DICT[symbol].append(latency_ms)

						if len(LATENCY_DICT[symbol]) >= LATENCY_SAMPLE_MIN:

							MEDIAN_LATENCY_DICT[symbol] = int(
								statistics.median(LATENCY_DICT[symbol])
							)

							if all(
								(	(len(LATENCY_DICT[s]) >= LATENCY_SAMPLE_MIN) and
									(
										statistics.median(LATENCY_DICT[s]) 
										< LATENCY_THRESHOLD_MS
									)
								)	for s in SYMBOLS
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

# ───────────────────────────────────────────────────────────────────────────────

def format_ws_url(
	url: str, label: str = ""
) -> str:

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

async def put_snapshot() -> None:	# @depth20@100ms snapshots
	
	""" ————————————————————————————————————————————————————————————————
	CORE FUNCTIONALITY:
		await SNAPSHOTS_QUEUE_DICT[symbol].put(snapshot)
	————————————————————————————————————————————————————————————————————
	HINT:
		asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
	————————————————————————————————————————————————————————————————————
	GLOBAL VARIABLES:
		WRITE:
			SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue]
			EVENT_1ST_SNAPSHOT:			asyncio.Event
		READ:
			LATENCY_GATE:
				EVENT_STREAM_ENABLE:	asyncio.Event
				LATENCY_DICT:			dict[str, deque[int]]
				MEDIAN_LATENCY_DICT:	dict[str, int]
			WEBSOCKETS:
				WS_URL, WS_PING_INTERVAL, WS_PING_TIMEOUT
				MAX_BACKOFF, BASE_BACKOFF,
				RESET_CYCLE_AFTER, RESET_BACKOFF_LEVEL
			LOGICAL:
				SYMBOLS
	———————————————————————————————————————————————————————————————— """

	ws_retry_cnt = 0

	while True:

		current_symbol = "UNKNOWN"

		try:
			async with websockets.connect(
				WS_URL,
				ping_interval = WS_PING_INTERVAL,
				ping_timeout  = WS_PING_TIMEOUT
			) as ws:

				logger.info(
					f"[put_snapshot] Connected to:\n"
					f"{format_ws_url(WS_URL, '(depth20@100ms)')}\n"
				)

				ws_retry_cnt = 0

				async for raw in ws:
					try:
						msg	= json.loads(raw)
						stream = msg.get("stream", "")
						current_symbol = (
							stream.split("@", 1)[0]
							or "UNKNOWN"
						).lower()

						# Guard: out-of-scope symbols
						if current_symbol not in SYMBOLS:
							continue

						# Gate closed or no latency samples yet? drop
						if (
							(not EVENT_STREAM_ENABLE.is_set()) or
							(not LATENCY_DICT.get(current_symbol, []))
						):
							continue

						data = msg.get("data", {})

						last_update = data.get("lastUpdateId")
						if last_update is None:
							continue

						bids = data.get("bids", [])
						asks = data.get("asks", [])

						# ──────────────────────────────────────────────────
						# Binance partial streams like `@depth20@100ms`
						# do NOT include the server-side event timestamp
						# ("E"). Thus, we must rely on local receipt time
						# corrected by estimated network latency.
						# ──────────────────────────────────────────────────
						
						lat_ms = max(
							0, MEDIAN_LATENCY_DICT.get(current_symbol, 0)
						)
						snapshot = {
							"lastUpdateId": last_update,
							"eventTime":	get_current_time_ms() - lat_ms,
							"bids": [[float(p), float(q)] for p, q in bids],
							"asks": [[float(p), float(q)] for p, q in asks],
						}

						# ──────────────────────────────────────────────────
						# `.qsize()` is less than or equal to one almost
						# surely, meaning that `SNAPSHOTS_QUEUE_DICT` is
						# being quickly consumed via `.get()`.
						# ──────────────────────────────────────────────────
						
						await SNAPSHOTS_QUEUE_DICT[current_symbol].put(snapshot)

						# 1st snapshot gate for FastAPI readiness
						
						if not EVENT_1ST_SNAPSHOT.is_set():
							EVENT_1ST_SNAPSHOT.set()

					except Exception as e:
						sym = (
							current_symbol
							if current_symbol in SYMBOLS
							else "UNKNOWN"
						)
						logger.warning(
							f"[put_snapshot][{sym.upper()}] "
							f"Failed to process message: {e}",
							exc_info=True
						)
						continue  # stay in websocket loop

		except asyncio.CancelledError:
			# propagate so caller can shut down gracefully
			raise

		except Exception as e:
			# websocket-level error → exponential backoff + retry
			ws_retry_cnt += 1
			sym = (
				current_symbol
				if current_symbol in SYMBOLS
				else "UNKNOWN"
			)

			logger.warning(
				f"[put_snapshot][{sym.upper()}] "
				f"WebSocket error "
				f"(ws_retry_cnt {ws_retry_cnt}): "
				f"{e}",
				exc_info=True
			)

			backoff = min(
				MAX_BACKOFF, BASE_BACKOFF * (2 ** ws_retry_cnt)
			) + random.uniform(0, 1)

			if ws_retry_cnt > RESET_CYCLE_AFTER:
				ws_retry_cnt = RESET_BACKOFF_LEVEL

			logger.warning(
				f"[put_snapshot][{sym.upper()}] "
				f"Retrying in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

		finally:
			# Informational close log; `async with` ensures ws is closed.
			# Use last known symbol purely for context (may be UNKNOWN).
			sym = (
				current_symbol
				if current_symbol in SYMBOLS
				else "UNKNOWN"
			)
			logger.info(
				f"[put_snapshot][{sym.upper()}] "
				f"WebSocket connection closed."
			)

# ───────────────────────────────────────────────────────────────────────────────

def symbol_consolidate_a_day(
	symbol:	  str,
	day_str:  str,
	base_dir: str,
	purge:	  bool = True
):

	with NanoTimer() as timer:

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
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
				f"Temp dir missing on {day_str}: {tmp_dir}"
			)

			return

		# List all zipped minute-level files (may be empty)

		try:

			zip_files = [f for f in os.listdir(tmp_dir) if f.endswith(".zip")]

		except Exception as e:

			logger.error(
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
				f"Failed to list zips in {tmp_dir}: {e}",
				exc_info=True
			)

			return

		if not zip_files:

			logger.error(
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
				f"No zip files to merge on {day_str}."
			)

			return

		# 🔧 File handle management with proper scope handling

		fout = None

		try:

			# Open output file for merged .jsonl content

			fout = open(merged_path, "w", encoding="utf-8")

			# Process each zip file in chronological order

			for zip_file in sorted(zip_files):

				zip_path = os.path.join(tmp_dir, zip_file)

				try:

					with zipfile.ZipFile(zip_path, "r") as zf:

						for member in zf.namelist():

							with zf.open(member) as f:

								for raw in f:

									fout.write(raw.decode("utf-8"))

				except Exception as e:

					logger.error(
						f"[symbol_consolidate_a_day][{symbol.upper()}] "
						f"Failed to extract {zip_path}: {e}",
						exc_info=True
					)

					return

		except Exception as e:

			logger.error(
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
				f"Failed to open or write to merged file {merged_path}: {e}",
				exc_info=True
			)

			return

		finally:

			# 🔧 Ensure the output file is properly closed

			if fout:

				try:

					fout.close()

				except Exception as close_error:

					logger.error(
						f"[symbol_consolidate_a_day][{symbol.upper()}] "
						f"Failed to close output file: {close_error}",
						exc_info=True
					)

		# Recompress the consolidated .jsonl into a final single-archive zip

		try:

			final_zip = merged_path.replace(".jsonl", ".zip")

			with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:

				zf.write(merged_path, arcname=os.path.basename(merged_path))

		except Exception as e:

			logger.error(
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
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
				f"[symbol_consolidate_a_day][{symbol.upper()}] "
				f"Failed to remove merged .jsonl on {day_str}: {e}",
				exc_info=True
			)

		# Optionally delete the original temp folder containing per-minute zips

		if purge:

			try:

				shutil.rmtree(tmp_dir)

			except Exception as e:

				logger.error(
					f"[symbol_consolidate_a_day][{symbol.upper()}] "
					f"Failed to remove temp dir {tmp_dir}: {e}",
					exc_info=True
				)

		logger.info(
			f"[symbol_consolidate_a_day][{symbol.upper()}] "
			f"Successfully merged {len(zip_files)} files for {day_str} "
			f"(took {timer.tock():.5f} sec)."
		)

# ───────────────────────────────────────────────────────────────────────────────

from concurrent.futures import ProcessPoolExecutor

#——————————————————————————————————————————————————————————————————

#	 '2025-06-27_13-15'
# -> '2025-06-27'
def get_date_from_suffix(
	suffix: str
) -> str:

	try: return suffix.split("_")[0]

	except Exception as e:

		logger.error(
			f"[{my_name()}] Failed to extract date "
			f"from suffix '{suffix}': {e}",
			exc_info=True
		)
		return "invalid_date"

#——————————————————————————————————————————————————————————————————

def safe_zip_n_remove_jsonl(
	lob_dir:	  str,
	symbol_upper: str,
	last_suffix:  str
):

#——————————————————————————————————————————————————————————————————

	def zip_and_remove(
		src_path: str
	):

		try:

			# `os.path.exists(src_path) == True` known by Caller

			zip_path = src_path.replace(".jsonl", ".zip")

			with zipfile.ZipFile(
				zip_path, "w",
				zipfile.ZIP_DEFLATED
			) as zf:

				zf.write(src_path,
					arcname=os.path.basename(src_path)
				)

			os.remove(src_path)

		except Exception as e:

			logger.error(
				f"[{my_name()}] Failed to zip "
				f"or remove '{src_path}': {e}",
				exc_info=True
			)

#——————————————————————————————————————————————————————————————————

	last_jsonl_path = os.path.join(
		os.path.join(
			lob_dir, "temporary",
			f"{symbol_upper}_orderbook_"
			f"{get_date_from_suffix(last_suffix)}",
		),
		f"{symbol_upper}_orderbook_{last_suffix}.jsonl"
	)

	if os.path.exists(last_jsonl_path):

		zip_and_remove(last_jsonl_path)

	else:

		logger.warning(
			f"[{my_name()}][{symbol_upper}] "
			f"File not found for compression: "
			f"{last_jsonl_path}"
		)

#——————————————————————————————————————————————————————————————————

async def symbol_dump_snapshot(
	symbol:					str,
	save_interval_min:		int,
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	event_stream_enable:	asyncio.Event,
	lob_dir:				str,
	symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
	json_flush_interval:	dict[str, int],
	latest_json_flush:		dict[str, int],
	purge_on_date_change:	int,
	merge_executor:			ProcessPoolExecutor,
	records_merged_dates:	dict[str, OrderedDict[str]],
	znr_executor:			ProcessPoolExecutor,
	records_znr_minutes:	dict[str, OrderedDict[str]],
	records_max:			int,
	logger:					logging.Logger
):

	#——————————————————————————————————————————————————————————————————

	def my_name():
		frame = inspect.stack()[1]
		return f"{frame.function}:{frame.lineno}"

	#——————————————————————————————————————————————————————————————————

	def safe_close_file_muted(f: TextIOWrapper):

		if f is not None and hasattr(f, 'close'):
			try:   f.close()
			except Exception: pass

	#——————————————————————————————————————————————————————————————————

	def safe_close_jsonl(
		f: TextIOWrapper
	) -> bool:
		
		try:
			
			f.close()
			return True

		except Exception as e:

			logger.error(f"[{my_name()}]"
				f"[{symbol.upper()}] "
				f"Close failed, retrying... "
				f"→ {e}",
				exc_info=True
			)
			safe_close_file_muted(f)
			return False

	#——————————————————————————————————————————————————————————————————
	
	def refresh_file_handle(
		file_path: str,
		suffix: str,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
		logger: logging.Logger
	) -> Optional[TextIOWrapper]:

		try:

			json_writer = open(
				file_path, "a",
				encoding="utf-8"
			)

		except OSError as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Open failed: {file_path} → {e}",
				exc_info=True
			)
			return None

		if json_writer is not None:

			try:

				symbol_to_file_handles[symbol] = (
					suffix, json_writer
				)

			except Exception as e:

				logger.error(
					f"[{my_name()}][{symbol.upper()}] "
					f"Failed to assign file handle: "
					f"{file_path} → {e}",
					exc_info=True
				)
				safe_close_jsonl(json_writer)
				return None

		return json_writer

	#——————————————————————————————————————————————————————————————————

	def pop_and_close_handle(
		handles: dict[str, tuple[str, TextIOWrapper]],
		symbol: str
	):

		tup = handles.pop(symbol, None)	# not only `pop` from dict

		if tup is not None:
			safe_close_file_muted(tup[1])		# but also `close`

	#——————————————————————————————————————————————————————————————————

	async def fetch_snapshot(
		queue:  asyncio.Queue,
		logger: logging.Logger,
		symbol: str
	) -> Optional[dict]:

		try:
			return await queue.get()
		
		except Exception as e:
			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to get snapshot from queue: {e}",
				exc_info=True
			)
			return None

	#——————————————————————————————————————————————————————————————————

	def get_file_suffix(
		interval_min: int,
		event_ts_ms: int
	) -> str:

		try:

			ts = ms_to_datetime(event_ts_ms)

			if interval_min >= 1440:

				return ts.strftime("%Y-%m-%d")

			else:

				return ts.strftime("%Y-%m-%d_%H-%M")

		except Exception as e:

			logger.error(
				f"[{my_name()}] Failed to generate suffix for "
				f"interval_min={interval_min}, "
				f"event_ts_ms={event_ts_ms}: {e}",
				exc_info=True
			)

			return "invalid_suffix"

	#——————————————————————————————————————————————————————————————————

	def get_suffix_n_date(
		save_interval_min: int,
		snapshot: dict,
		symbol: str
	) -> tuple[Optional[str], Optional[str]]:
		
		try:

			suffix = get_file_suffix(
				save_interval_min,
				snapshot.get(
					"eventTime",
					get_current_time_ms()
				)
			)

			date_str = get_date_from_suffix(suffix)

			return suffix, date_str
		
		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to compute suffix/day: {e}",
				exc_info=True
			)

			return None, None
	
	#——————————————————————————————————————————————————————————————————

	def gen_file_path(
		symbol_upper: str,
		suffix:   str,
		lob_dir:  str,
		date_str: str
	) -> Optional[str]:
		
		try:

			file_name = f"{symbol_upper}_orderbook_{suffix}.jsonl"
			temp_dir  = os.path.join(lob_dir, "temporary",
				f"{symbol_upper}_orderbook_{date_str}",
			)
			os.makedirs(temp_dir, exist_ok=True)
			return os.path.join(temp_dir, file_name)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to build file path: {e}",
				exc_info=True
			)
			return None

	#——————————————————————————————————————————————————————————————————

	def flush_snapshot(
		json_writer: TextIOWrapper,
		snapshot: dict,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
		json_flush_interval: dict[str, int],
		latest_json_flush: dict[str, int],
		file_path: str,
		logger: logging.Logger
	) -> bool:

		try:

			json_writer.write(
				json.dumps(snapshot, 
					separators=(",", ":")
				) + "\n"
			)
			json_writer.flush()

			current_time = get_current_time_ms()

			json_flush_interval[symbol] = (
				current_time - latest_json_flush[symbol]
			)
			
			latest_json_flush[symbol] = current_time

			return True

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Write failed: {file_path} → {e}",
				exc_info=True
			)

			try:

				# Invalidate `json_writer` for next iteration
				pop_and_close_handle(
					symbol_to_file_handles, symbol
				)

			except Exception: pass

			return False
		
	#——————————————————————————————————————————————————————————————————

	def memorize_treated(
		records: dict[str, OrderedDict[str]],
		records_max: int,
		symbol: str,
		to_rec: str
	):

		# discard the oldest at the front of the OrderedDict
		if len(records[symbol]) >= records_max:
			records[symbol].popitem(last=False)
		records[symbol][to_rec] = None

	#——————————————————————————————————————————————————————————————————

	queue = snapshots_queue_dict[symbol]
	symbol_upper = symbol.upper()

	while True:

		#——————————————————————————————————————————————————————————————

		snapshot = await fetch_snapshot(
			queue, logger, symbol
		)
		
		if snapshot is None:
			logger.warning(
				f"[{my_name()}][{symbol_upper}] "
				f"Snapshot is None, skipping iteration."
			)
			continue

		if not event_stream_enable.is_set():
			continue
		
		suffix, date_str = get_suffix_n_date(
			save_interval_min,
			snapshot, symbol
		)

		if ((suffix is None) or (date_str is None)):
			logger.warning(
				f"[{my_name()}][{symbol_upper}] "
				f"Suffix or date string is None, "
				f"skipping iteration."
			)
			continue

		file_path = gen_file_path(
			symbol_upper, suffix,
			lob_dir, date_str
		)
		
		if file_path is None:
			logger.warning(
				f"[{my_name()}][{symbol_upper}] "
				f"File path is None, "
				f"skipping iteration."
			)
			continue

		# ────────────────────────────────────────────────────────────────────
		# STEP 1: Roll-over by Minute
		# ────────────────────────────────────────────────────────────────────
		# `last_suffix` will be `None` at the beginning.
		# ────────────────────────────────────────────────────────────────────

		last_suffix, json_writer = symbol_to_file_handles.get(
			symbol, (None, None))

		if last_suffix != suffix:

			if json_writer:							  # if not the first flush

				# ────────────────────────────────────────────────────────────

				if not safe_close_jsonl(json_writer):

					logger.warning(
						f"[{my_name()}][{symbol.upper()}] "
						f"JSON writer may not "
						f"have been closed."
					)

				del json_writer

				# ────────────────────────────────────────────────────────────
				# fire and forget
				# ────────────────────────────────────────────────────────────

				if last_suffix not in records_znr_minutes[symbol]:

					memorize_treated(
						records_znr_minutes,
						records_max,
						symbol, last_suffix
					)

					znr_executor.submit(			# pickle
						safe_zip_n_remove_jsonl,
						lob_dir, symbol_upper, 
						last_suffix
					)

			# ────────────────────────────────────────────────────────────────

			try: 
				
				json_writer = refresh_file_handle(
					file_path, suffix, symbol, 
					symbol_to_file_handles,
					logger
				)
				if json_writer is None: continue 

			except Exception as e:

				logger.error(
					f"[{my_name()}][{symbol_upper}] "
					f"Failed to refresh file handles → {e}",
					exc_info=True
				)
				continue

		# ────────────────────────────────────────────────────────────────────
		# STEP 2: Check for day rollover and trigger merge
		# At this point, ALL previous files are guaranteed to be .zip
		# ────────────────────────────────────────────────────────────────────

		try:

			if last_suffix:

				last_date = get_date_from_suffix(last_suffix)

				if ((last_date != date_str) and 
					(last_date not in records_merged_dates[symbol])
				):

					memorize_treated(
						records_merged_dates,
						records_max,
						symbol, last_date
					)
					
					merge_executor.submit(			# pickle
						symbol_consolidate_a_day,	# TODO: defined in global
						symbol, last_date, lob_dir,
						purge_on_date_change == 1
					)

					logger.info(
						f"[{my_name()}][{symbol_upper}] "
						f"Triggered merge for {last_date} "
						f"(current day: {date_str})."
					)

					del last_date

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to check/trigger merge: {e}",
				exc_info=True
			)

			if 'last_date' in locals(): del last_date
			del e
			continue

		finally:

			del date_str, last_suffix

		# ────────────────────────────────────────────────────────────────────
		# STEP 3: Write snapshot to file and update flush intervals
		# This step ensures the snapshot is saved and flush intervals are updated.
		# ────────────────────────────────────────────────────────────────────

		if not flush_snapshot(
			json_writer,
			snapshot,
			symbol,
			symbol_to_file_handles,
			json_flush_interval,
			latest_json_flush,
			file_path,
			logger
		):

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to flush snapshot.",
				exc_info=True
			)

		del snapshot, file_path


























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

	try:
		MERGE_EXECUTOR.shutdown(wait=True)
		logger.info(f"[main] MERGE_EXECUTOR shutdown safely complete.")

	except Exception as e:
		logger.error(
			f"[main] MERGE_EXECUTOR shutdown failed: {e}",
			exc_info=True
		)
	try:
		ZNR_EXECUTOR.shutdown(wait=True)
		logger.info(f"[main] ZNR_EXECUTOR shutdown safely complete.")

	except Exception as e:
		logger.error(
			f"[main] ZNR_EXECUTOR shutdown failed: {e}",
			exc_info=True
		)

atexit.register(shutdown_merge_executor)

# ───────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(APP):

	try:

		# Startup logic (if any) goes here

		yield

	except KeyboardInterrupt:

		logger.info("[lifespan] Application terminated by user (Ctrl + C).")

	except Exception as e:

		logger.error(f"[lifespan] Unhandled exception: {e}", exc_info=True)

	finally:

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
#
#	  - Logging is routed via `uvicorn.error`, managed by FastAPI's ASGI server.
#	  - Our logger (`logger = logging.getLogger("uvicorn.error")`) is active
#		and functional as soon as FastAPI is imported, even before APP launch.
#
#   2. 🌐 REST API Endpoints:
#
#	  - Provides health checks, JSON-based order book access,
# 		and real-time UI rendering.
#
# ⚠️ Removal of FastAPI would break:
#
#	  - Logging infrastructure
#	  - HTML endpoint: /dashboard
#
#   - Even if not all FastAPI features are always used,
# 	  its presence is mandatory.
#
#   - Template directory is resolved via `resource_path()`
# 	  for PyInstaller compatibility.
#
#   - See also: RULESET.md for documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

APP = FastAPI(lifespan=lifespan)

# ───────────────────────────────────────────────────────────────────────────────
# EXTERNAL DASHBOARD SERVICE
# ───────────────────────────────────────────────────────────────────────────────

@APP.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
	"""Dashboard HTML 페이지 서빙"""
	try:
		# HTML 파일 경로를 resource_path를 통해 가져오기
		html_path = resource_path(
			"stream_binance_dashboard.html",
			logger
		)

		if not os.path.exists(html_path):
			logger.error(f"[dashboard_page] HTML file not found: {html_path}")
			raise HTTPException(status_code=500, detail="Dashboard HTML file missing")

		# HTML 파일 읽기
		with open(html_path, "r", encoding="utf-8") as f:
			dashboard_html = f.read()

		return HTMLResponse(content=dashboard_html)

	except Exception as e:
		logger.error(f"[dashboard_page] Failed to serve dashboard: {e}", exc_info=True)
		raise HTTPException(status_code=500, detail="Internal server error")

# ───────────────────────────────────────────────────────────────────────────────
# 📊 Dashboard Monitoring & WebSocket Stream Handler
#
# Provides real-time monitoring and WebSocket streaming for system metrics,
# such as hardware usage and median latency per symbol, to connected clients.
#
# Features:
#	• Hardware Monitoring:
#		- Tracks CPU, memory, storage, and network usage using `psutil`.
#		- Updates global metrics asynchronously to avoid blocking the event loop.
#
#	• WebSocket Dashboard:
#		- Streams monitoring data to clients at `/ws/dashboard`.
#		- Enforces connection limits (`MAX_DASHBOARD_CONNECTIONS`)
#		  and session timeouts.
#		- Periodically sends JSON payloads with hardware metrics and
#		  symbol latency.
#
#	• Configuration-Driven:
#		- All limits, intervals, and backoff strategies are loaded from `.conf`.
#		- Fully customizable via `get_binance_chart.conf`.
#
# Usage:
#	- Designed for extensibility: add more metrics or endpoints as needed.
#	- Intended for browser-based dashboards or monitoring tools.
#
# Safety & Robustness:
#	- Hardware monitoring runs asynchronously to prevent blocking.
#	- WebSocket handler ensures graceful handling of disconnects,
#	  errors, and cancellations.
#	- Implements exponential backoff for reconnection attempts.
#	- All resource management (locks, counters) is thread-safe.
#
# Structures:
#	• Global Metrics:
#		- NETWORK_LOAD_MBPS: Network bandwidth usage in Mbps.
#		- CPU_LOAD_PERCENTAGE: CPU usage percentage.
#		- MEM_LOAD_PERCENTAGE: Memory usage percentage.
#		- STORAGE_PERCENTAGE: Storage usage percentage.
#
#	• WebSocket Configuration:
#		- DASHBOARD_STREAM_INTERVAL: Interval between data pushes (seconds).
#		- MAX_DASHBOARD_CONNECTIONS: Max concurrent WebSocket connections.
#		- MAX_DASHBOARD_SESSION_SEC: Max session duration per client (seconds).
#
#	• Locks:
#		- ACTIVE_DASHBOARD_LOCK: Ensures thread-safe connection tracking.
#
# See also:
#	- monitor_hardware(): Asynchronous hardware monitoring function.
#	- dashboard(): WebSocket handler for dashboard clients.
#	- RULESET.md: Documentation and code conventions.
# ───────────────────────────────────────────────────────────────────────────────

from fastapi import WebSocket, WebSocketDisconnect
import psutil

DASHBOARD_STREAM_INTERVAL = float(CONFIG.get("DASHBOARD_STREAM_INTERVAL", 0.075))
MAX_DASHBOARD_CONNECTIONS = int(CONFIG.get("MAX_DASHBOARD_CONNECTIONS", 3))
MAX_DASHBOARD_SESSION_SEC = int(CONFIG.get("MAX_DASHBOARD_SESSION_SEC", 1800))

ACTIVE_DASHBOARD_LOCK		 = asyncio.Lock()
ACTIVE_DASHBOARD_CONNECTIONS = 0

HARDWARE_MONITORING_INTERVAL = float(
	CONFIG.get("HARDWARE_MONITORING_INTERVAL", 1.0)
)

CPU_PERCENT_DURATION = float(
	CONFIG.get("CPU_PERCENT_DURATION", 0.2)
)

NETWORK_LOAD_MBPS:		int   = 0
CPU_LOAD_PERCENTAGE:	float = 0.0
MEM_LOAD_PERCENTAGE:	float = 0.0
STORAGE_PERCENTAGE:		float = 0.0
GC_TIME_COST_MS:		float = -0.0

GC_INTERVAL_SEC = float(
	CONFIG.get("GC_INTERVAL_SEC", 60.0)
)

DESIRED_MAX_SYS_MEM_LOAD = float(
	CONFIG.get("DESIRED_MAX_SYS_MEM_LOAD", 85.0)
)

# ───────────────────────────────────────────────────────────────────────────────
# async def periodic_gc():
	# import gc
	# global GC_INTERVAL_SEC, GC_TIME_COST_MS, EVENT_STREAM_ENABLE
	# await EVENT_STREAM_ENABLE.wait()
	# while True:
		# try:
			# with NanoTimer() as timer:
				# await asyncio.to_thread(gc.collect)
				# GC_TIME_COST_MS = (
					# timer.tock() * 1_000.0
				# )
		# except Exception as e:
			# logger.error(
				# f"[periodic_gc] "
				# f"Error during gc.collect(): {e}",
				# exc_info=True
			# )
		# finally:
			# await asyncio.sleep(GC_INTERVAL_SEC)
# ───────────────────────────────────────────────────────────────────────────────

async def monitor_hardware():

	"""
	Hardware monitoring function that runs as an async coroutine.
	Updates global hardware metrics using psutil with non-blocking operations.
	For details, see `https://psutil.readthedocs.io/en/latest/`.

	Metrics updated:
		- NETWORK_LOAD_MBPS:   Network bandwidth in megabits per second
		- CPU_LOAD_PERCENTAGE: CPU load percentage
		- MEM_LOAD_PERCENTAGE: Memory usage percentage
		- STORAGE_PERCENTAGE: Storage usage percentage
	"""

	global NETWORK_LOAD_MBPS, CPU_LOAD_PERCENTAGE
	global MEM_LOAD_PERCENTAGE, STORAGE_PERCENTAGE
	global HARDWARE_MONITORING_INTERVAL, CPU_PERCENT_DURATION
	global DESIRED_MAX_SYS_MEM_LOAD
	
	# Initialize previous network counters for bandwidth calculation

	prev_counters = psutil.net_io_counters()
	prev_sent	  = prev_counters.bytes_sent
	prev_recv	  = prev_counters.bytes_recv
	prev_time	  = time.time()
	
	logger.info(
		f"[monitor_hardware] "
		f"Hardware monitoring started."
	)
	
	while True:

		try:
			
			wt_start = time.time()

			# CPU Usage: blocking call to get CPU load percentage

			CPU_LOAD_PERCENTAGE = await asyncio.to_thread(
				psutil.cpu_percent, 
				interval=CPU_PERCENT_DURATION
			)
			
			# Memory Usage

			memory_info = await asyncio.to_thread(psutil.virtual_memory)
			MEM_LOAD_PERCENTAGE = memory_info.percent
			
			# Storage Usage (root filesystem)

			disk_info = await asyncio.to_thread(psutil.disk_usage, '/')
			STORAGE_PERCENTAGE = disk_info.percent
			
			# Network Usage (Mbps)

			curr_time = time.time()
			counters  = await asyncio.to_thread(psutil.net_io_counters)
			curr_sent = counters.bytes_sent
			curr_recv = counters.bytes_recv
			
			# Calculate bytes transferred since last measurement

			sent_diff = curr_sent - prev_sent
			recv_diff = curr_recv - prev_recv
			time_diff = curr_time - prev_time
			
			# Convert to Mbps

			if time_diff > 0:

				total_bytes = sent_diff + recv_diff
				NETWORK_LOAD_MBPS = (
					(total_bytes * 8) / (time_diff * 1_000_000)
				)
			
			# Update previous values

			prev_sent = curr_sent
			prev_recv = curr_recv
			prev_time = curr_time

			# High Memory Load Warning
			# Disabled for now since it can confuse memray
			
			#if MEM_LOAD_PERCENTAGE > DESIRED_MAX_SYS_MEM_LOAD:
			#
			#	logger.warning(
			#		f"[monitor_hardware]\n"
			#		f"\t  {MEM_LOAD_PERCENTAGE:.2f}% "
			#		f"(MEM_LOAD_PERCENTAGE)\n"
			#		f"\t> {DESIRED_MAX_SYS_MEM_LOAD:.2f}% "
			#		f"(DESIRED_MAX_SYS_MEM_LOAD)."
			#	)
			
		except Exception as e:

			logger.error(
				f"[monitor_hardware] "
				f"Error monitoring hardware: {e}",
				exc_info=True
			)

		finally:

			sleep_duration = max(
				0.0, HARDWARE_MONITORING_INTERVAL - (time.time() - wt_start)
			)

			await asyncio.sleep(sleep_duration)

# ───────────────────────────────────────────────────────────────────────────────

@APP.websocket("/ws/dashboard")
async def dashboard(websocket: WebSocket):

	"""
	📊 Streams dashboard monitoring data to WebSocket clients.

	🛠️ Features:
	- Logs disconnects and errors, then waits before allowing reconnection.
	- Designed for extensibility: supports adding more metrics as needed.

	📌 Notes:
	- Handles connection limits and session timeouts gracefully.
	- Ensures thread-safe resource management for active connections.
	"""

	global DASHBOARD_STREAM_INTERVAL, MAX_DASHBOARD_CONNECTIONS
	global ACTIVE_DASHBOARD_CONNECTIONS, ACTIVE_DASHBOARD_LOCK

	global SYMBOLS, MEDIAN_LATENCY_DICT, JSON_FLUSH_INTERVAL
	global NETWORK_LOAD_MBPS, CPU_LOAD_PERCENTAGE
	global MEM_LOAD_PERCENTAGE, STORAGE_PERCENTAGE
	global GC_TIME_COST_MS

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
						"[dashboard] "
						"Connection refused: too many clients."
					)
					return

				ACTIVE_DASHBOARD_CONNECTIONS += 1

			try:

				# Attempt to accept a new WebSocket connection
				# from a dashboard client

				await websocket.accept()
				reconnect_attempt = 0		# Reset backoff on successful accept

				# Track session start time for session timeout
				
				start_time_ms  = get_current_time_ms()
				
				max_session_ms = (
					MAX_DASHBOARD_SESSION_SEC * 1000 if MAX_DASHBOARD_SESSION_SEC > 0
					else None
				)
				
				# Main data push loop: send metrics until client disconnects, 
				# error, or session timeout

				while True:

					try:
						# Construct the monitoring payload
						# add more fields as needed

						data = {
							"med_latency": {
								symbol: MEDIAN_LATENCY_DICT.get(symbol, 0)
								for symbol in SYMBOLS
							},
							"flush_interval": {
								symbol: JSON_FLUSH_INTERVAL.get(symbol, 0)
								for symbol in SYMBOLS
							},
							"queue_size": {
								symbol: SNAPSHOTS_QUEUE_DICT[symbol].qsize()
								for symbol in SYMBOLS
							},
							"queue_size_total": sum(
								SNAPSHOTS_QUEUE_DICT[symbol].qsize()
								for symbol in SYMBOLS
							),
							"hardware": {
								"network_mbps":	   round(NETWORK_LOAD_MBPS, 2),
								"cpu_percent":	   CPU_LOAD_PERCENTAGE,
								"memory_percent":  MEM_LOAD_PERCENTAGE,
								"storage_percent": STORAGE_PERCENTAGE
							},
							"gc_time_cost_ms": GC_TIME_COST_MS,
							"last_updated": ms_to_datetime(
								get_current_time_ms()
							).isoformat()
						}

						# Send the JSON payload to the connected client

						await websocket.send_json(data)

						# Check session duration only if MAX_DASHBOARD_SESSION_SEC > 0
						
						if max_session_ms is not None:
							
							current_time_ms = get_current_time_ms()
							
							if current_time_ms - start_time_ms > max_session_ms:
								
								await websocket.close(
									code=1000,
									reason="Session time limit reached."
								)
								
								break

						# Wait for the configured interval before sending the next update

						await asyncio.sleep(DASHBOARD_STREAM_INTERVAL)

					except WebSocketDisconnect:

						# Client closed the connection (normal case)

						logger.info(
							f"[dashboard] "
							f"WebSocket client disconnected."
						)
						break

					except asyncio.CancelledError:

						# Task was cancelled (e.g., server shutdown)

						logger.info(
							f"[dashboard] "
							f"WebSocket handler task cancelled."
						)
						break

					except Exception as e:

						# Log unexpected errors, then break to allow reconnection

						logger.warning(
							f"[dashboard] WebSocket error: {e}",
							exc_info=True
						)
						break

				# Exit inner loop: client disconnected, error, or session timeout
				# Outer loop allows for reconnection attempts if desired

				break	# Remove this break to allow
						# the same client to reconnect in-place

			finally:

				# ── Decrement connection count on disconnect or error

				async with ACTIVE_DASHBOARD_LOCK:
					ACTIVE_DASHBOARD_CONNECTIONS -= 1

		except Exception as e:

			# Accept failed (e.g., handshake error, resource exhaustion)

			reconnect_attempt += 1
			logger.warning(
				f"[dashboard] "
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
				f"[dashboard] "
				f"Retrying accept in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

# ───────────────────────────────────────────────────────────────────────────────
# ⏱️ Timed Watchdog for Graceful Profiling Shutdown
# ───────────────────────────────────────────────────────────────────────────────

def graceful_shutdown():

	"""
	Graceful shutdown function for profiling mode.
	"""

	try:

		# Close all file handles

		for symbol in SYMBOLS:

			suffix_writer = SYMBOL_TO_FILE_HANDLES.get(symbol)

			if suffix_writer:

				suffix, writer = suffix_writer

				try:

					if writer:
						writer.close()

					logger.info(
						f"[graceful_shutdown] Closed file for {symbol}"
					)

				except Exception as e:

					logger.error(
						f"[graceful_shutdown] "
						f"Failed to close file for {symbol}: {e}"
					)
		
		shutdown_merge_executor()
		
		logger.info(
			f"[graceful_shutdown] Graceful shutdown completed."
		)
		
	except Exception as e:

		logger.error(
			f"[graceful_shutdown] Error during shutdown: {e}"
		)

# ───────────────────────────────────────────────────────────────────────────────
# 🚦 Main Entrypoint & Async Task Orchestration
# ───────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

	from uvicorn.config import Config
	from uvicorn.server import Server
	import asyncio

	# ───────────────────────────────────────────────────────────────────────────
	# THESE TWO MUST BE WITHIN THE MAIN PROCESS
	# ───────────────────────────────────────────────────────────────────────────

	MERGE_EXECUTOR = ProcessPoolExecutor(max_workers=len(SYMBOLS))
	ZNR_EXECUTOR   = ProcessPoolExecutor(max_workers=len(SYMBOLS))

	# ───────────────────────────────────────────────────────────────────────────

	async def main():

		try:

			# Initialize in-memory structures

			global EVENT_1ST_SNAPSHOT

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

			# Launch a periodic garbage collection coroutine
			# try:
				# asyncio.create_task(periodic_gc())
				# logger.info(
					# f"[main] periodic_gc task launched "
					# f"(every {GC_INTERVAL_SEC:.1f}s)."
				# )
			# except Exception as e:
				# logger.error(
					# f"[main] Failed to launch periodic_gc: {e}",
					# exc_info=True
				# )
				# sys.exit(1)

			# Launch hardware monitoring in a coroutine

			try:

				asyncio.create_task(monitor_hardware())
				logger.info(f"[main] Hardware monitoring task launched.")

			except Exception as e:

				logger.error(
					f"[main] Failed to launch hardware monitoring: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Launch background tasks
			# Handles periodic snapshot persistence per symbol

			try:

				for symbol in SYMBOLS:

					asyncio.create_task(
						symbol_dump_snapshot(
							symbol,
							SAVE_INTERVAL_MIN,
							SNAPSHOTS_QUEUE_DICT,
							EVENT_STREAM_ENABLE,
							LOB_DIR,
							SYMBOL_TO_FILE_HANDLES,
							JSON_FLUSH_INTERVAL,
							LATEST_JSON_FLUSH,
							PURGE_ON_DATE_CHANGE,
							MERGE_EXECUTOR, RECORDS_MERGED_DATES,
							ZNR_EXECUTOR,   RECORDS_ZNR_MINUTES,
							RECORDS_MAX,
							logger
						)
					)

			except Exception as e:

				logger.error(
					f"[main] Failed to launch symbol_dump_snapshot tasks: {e}",
					exc_info=True
				)

				sys.exit(1)

			# Streams and stores depth20@100ms

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

			# Wait for at least one valid snapshot before serving

			try:

				await EVENT_1ST_SNAPSHOT.wait()

			except Exception as e:

				logger.error(
					f"[main] Error while waiting for EVENT_1ST_SNAPSHOT: {e}",
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
					port		= 8000,			# todo: avoid hardcoding
					lifespan	= "on",
					use_colors	= True,
					log_level	= "warning",
					workers		= os.cpu_count(),
					loop		= "asyncio",	# todo: `uvicorn` if Linux
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

""" ————————————————————————————————————————————————————————————————————————————

Infinite Coroutines in the Main Process:

	SNAPSHOT:
		✅ async def put_snapshot() -> None
		✅ async def symbol_dump_snapshot(symbol: str) -> None
		- perfectly understand both functions via flow chart generation

	LATENCY:
		async def estimate_latency() -> None
		async def gate_streaming_by_latency() -> None
		- probably, refactor as logical threads

	DASHBOARD:
		async def dashboard(websocket: WebSocket)
		async def monitor_hardware()

	DEPRECATED:
		async def periodic_gc()

————————————————————————————————————————————————————————————————————————————————

The `memray` Python module @VS Code WSL2 Terminal:
	sudo apt update
	sudo apt install -y build-essential python3-dev cargo
	pip install --upgrade pip setuptools wheel
	pip install memray

Run `memray` as follows:
	memray run -o memleak_trace.bin stream_binance.py
	memray flamegraph memleak_trace.bin -o memleak_report.html
	memray stats memleak_trace.bin

————————————————————————————————————————————————————————————————————————————————

Dashboard URLs:
- http://localhost:8000/dashboard		dev pc
- http://192.168.1.107/dashboard		server (internal access)
- http://c01hyka.duckdns.org/dashboard	server (external access)

———————————————————————————————————————————————————————————————————————————— """