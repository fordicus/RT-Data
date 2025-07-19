# stream_binance.py

r"""———————————————————————————————————————————————————————————————

Dashboard URLs:
	http://localhost:8000/dashboard			dev pc
	http://192.168.1.107/dashboard			internal server
	http://c01hyka.duckdns.org/dashboard	external server

BinanceWsMan:
	https://tinyurl.com/BinanceWsMan

Binance websocket:
	wss://stream.binance.com:9443/stream?
		streams={symbol}@depth20@100ms

———————————————————————————————————————————————————————————————————

Dependency:
	python==3.9.23
	pyinstaller==6.14.2
	pyinstaller==hooks-contrib-2025.5
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	psutil==7.0.0
	memray==1.17.2

————————————————————————————————————————————————————————————————"""

from util import (
	my_name,			   # For exceptions with 0 Lebesgue measure
	resource_path,
	get_current_time_ms,
	ms_to_datetime,
	load_config,
	format_ws_url,
	set_global_logger,
)

from core import (
	put_snapshot,
	symbol_dump_snapshot,
)

import os, time, random, statistics
import websockets, asyncio, certifi, json
from datetime import datetime, timezone
from collections import deque
from io import TextIOWrapper
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

os.environ["SSL_CERT_FILE"] = certifi.where()
logger, queue_listener = set_global_logger()

#——————————————————————————————————————————————————————————————————

try:
	(
		CONFIG, SYMBOLS, WS_URL, LOB_DIR, PURGE_ON_DATE_CHANGE,
		BASE_BACKOFF, MAX_BACKOFF, RESET_CYCLE_AFTER,
		RESET_BACKOFF_LEVEL, DASHBOARD_STREAM_INTERVAL,
		MAX_DASHBOARD_CONNECTIONS, MAX_DASHBOARD_SESSION_SEC,
		HARDWARE_MONITORING_INTERVAL, CPU_PERCENT_DURATION,
		DESIRED_MAX_SYS_MEM_LOAD, LATENCY_DEQUE_SIZE,
		LATENCY_SAMPLE_MIN, LATENCY_THRESHOLD_MS,
		LATENCY_SIGNAL_SLEEP, LATENCY_GATE_SLEEP,
		WS_PING_INTERVAL, WS_PING_TIMEOUT
	) = load_config(logger)

except Exception as e:

	logger.critical(
		f"[load_config] Failed to load config: {e}"
		f"Application cannot start.",
		exc_info=True
	)
	raise SystemExit()

#——————————————————————————————————————————————————————————————————
# 🧠 Runtime Per-Symbol State
#——————————————————————————————————————————————————————————————————

LATENCY_DICT:		  dict[str, deque[int]] = {}
MEDIAN_LATENCY_DICT:  dict[str, int] = {}
DEPTH_UPDATE_ID_DICT: dict[str, int] = {}
LATEST_JSON_FLUSH:	  dict[str, int] = {}
JSON_FLUSH_INTERVAL:  dict[str, int] = {}

EVENT_1ST_SNAPSHOT:	 asyncio.Event
EVENT_LATENCY_VALID: asyncio.Event
EVENT_STREAM_ENABLE: asyncio.Event

EVENT_FLAGS_INITIALIZED = False

def initialize_event_flags():

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

		raise SystemExit("Failed to initialize event flags.")

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

		raise SystemExit("Event flags not initialized. Application cannot proceed.")

# ───────────────────────────────────────────────────────────────────────────────
# 📦 Runtime Memory Buffers & Async File Handles
# ───────────────────────────────────────────────────────────────────────────────

SNAPSHOTS_QUEUE_DICT:   dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]] = {}

RECORDS_MERGED_DATES: dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:  dict[str, OrderedDict[str]] = {}	# ZNR := zip_n_remove

# ───────────────────────────────────────────────────────────────────────────────

def initialize_runtime_state(
	snapshots_queue_max: int = 100
):

	try:
		global SYMBOLS
		global LATENCY_DICT, MEDIAN_LATENCY_DICT, DEPTH_UPDATE_ID_DICT
		global LATEST_JSON_FLUSH, JSON_FLUSH_INTERVAL
		global SNAPSHOTS_QUEUE_DICT

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
			symbol: asyncio.Queue(maxsize=snapshots_queue_max)
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
		raise SystemExit("Failed to initialize runtime state.")

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

ACTIVE_DASHBOARD_LOCK		 = asyncio.Lock()
ACTIVE_DASHBOARD_CONNECTIONS = 0

NETWORK_LOAD_MBPS:		int   = 0
CPU_LOAD_PERCENTAGE:	float = 0.0
MEM_LOAD_PERCENTAGE:	float = 0.0
STORAGE_PERCENTAGE:		float = 0.0
GC_TIME_COST_MS:		float = -0.0

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

			initialize_runtime_state()
			initialize_event_flags()
			assert_event_flags_initialized()

			try:

				tasks = [
					asyncio.create_task(monitor_hardware()),
					asyncio.create_task(estimate_latency()),
					asyncio.create_task(gate_streaming_by_latency()),
				]

			except Exception as e:

				logger.critical(
					f"[main] Unhandled exception: {e}",
					exc_info=True
				)
				raise SystemExit("Unhandled exception during task creation.")

			try:

				asyncio.create_task(
					put_snapshot(	# @depth20@100ms snapshots
						SNAPSHOTS_QUEUE_DICT,
						EVENT_STREAM_ENABLE,
						LATENCY_DICT,
						MEDIAN_LATENCY_DICT,
						EVENT_1ST_SNAPSHOT,
						MAX_BACKOFF, 
						BASE_BACKOFF,
						RESET_CYCLE_AFTER,
						RESET_BACKOFF_LEVEL,
						WS_URL,
						WS_PING_INTERVAL,
						WS_PING_TIMEOUT,
						SYMBOLS,
						logger,
					)
				)

				for symbol in SYMBOLS:

					asyncio.create_task(
						symbol_dump_snapshot(
							symbol,
							SNAPSHOTS_QUEUE_DICT,
							EVENT_STREAM_ENABLE,
							LOB_DIR,
							SYMBOL_TO_FILE_HANDLES,
							JSON_FLUSH_INTERVAL,
							LATEST_JSON_FLUSH,
							PURGE_ON_DATE_CHANGE,
							MERGE_EXECUTOR, RECORDS_MERGED_DATES,
							ZNR_EXECUTOR,   RECORDS_ZNR_MINUTES,
							logger,
						)
					)

			except Exception as e:

				logger.error(
					f"[main] Failed to launch symbol_dump_snapshot tasks: {e}",
					exc_info=True
				)

				raise SystemExit("Failed to launch symbol_dump_snapshot tasks.")

			# Wait for at least one valid snapshot before serving

			try:

				await EVENT_1ST_SNAPSHOT.wait()

			except Exception as e:

				logger.error(
					f"[main] Error while waiting for EVENT_1ST_SNAPSHOT: {e}",
					exc_info=True
				)

				raise SystemExit("Error while waiting for the first snapshot.")

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

				raise SystemExit("FastAPI server failed to start.")

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
		raise SystemExit("Unhandled exception in main application.")

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

———————————————————————————————————————————————————————————————————————————— """