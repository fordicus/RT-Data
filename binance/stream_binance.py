# stream_binance.py

r"""————————————————————————————————————————————————————————————————————————————

Dashboard URLs:
	http://localhost:8000/dashboard			dev pc
	http://192.168.1.107/dashboard			internal server
	http://c01hyka.duckdns.org/dashboard	external server

BinanceWsMan:
	https://tinyurl.com/BinanceWsMan

Binance websocket:
	wss://stream.binance.com:9443/stream?
		streams={symbol}@depth20@100ms

————————————————————————————————————————————————————————————————————————————————

Dependency:
	python==3.9.23
	pyinstaller==6.14.2
	pyinstaller==hooks-contrib-2025.5
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	psutil==7.0.0
	memray==1.17.2

—————————————————————————————————————————————————————————————————————————————"""

from init import (
	load_config,
	init_runtime_state,
)

from shutdown import (
	create_shutdown_manager
)

from util import (
	my_name,				# For exceptions with 0 Lebesgue measure
	resource_path,
	get_current_time_ms,
	ms_to_datetime,
	format_ws_url,
	set_global_logger,
)

from latency import (
	gate_streaming_by_latency,
	estimate_latency,
)

from core import (
	put_snapshot,
	symbol_dump_snapshot,
)

from dashboard import (
	monitor_hardware,
)

import os, time, random, logging
import asyncio, certifi
from datetime import datetime, timezone
from collections import deque
from io import TextIOWrapper
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

os.environ["SSL_CERT_FILE"] = certifi.where()

logger, queue_listener = set_global_logger()

(
	SYMBOLS,
	WS_URL,
	#
	LOB_DIR,
	#
	PURGE_ON_DATE_CHANGE, SAVE_INTERVAL_MIN,
	#
	SNAPSHOTS_QUEUE_MAX, RECORDS_MAX,
	#
	LATENCY_DEQUE_SIZE, LATENCY_SAMPLE_MIN,
	LATENCY_THRESHOLD_MS, LATENCY_SIGNAL_SLEEP,
	#
	BASE_BACKOFF, MAX_BACKOFF,
	RESET_CYCLE_AFTER, RESET_BACKOFF_LEVEL,
	#
	WS_PING_INTERVAL, WS_PING_TIMEOUT,
	#
	DASHBOARD_STREAM_INTERVAL,
	MAX_DASHBOARD_CONNECTIONS,
	MAX_DASHBOARD_SESSION_SEC,
	HARDWARE_MONITORING_INTERVAL,
	CPU_PERCENT_DURATION,
	DESIRED_MAX_SYS_MEM_LOAD
	#
) = load_config(logger)

#———————————————————————————————————————————————————————————————————————————————
# TODO
#———————————————————————————————————————————————————————————————————————————————

SNAPSHOTS_QUEUE_DICT:   dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]] = {}

RECORDS_MERGED_DATES:	dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:	dict[str, OrderedDict[str]] = {}

LATENCY_DICT:			dict[str, deque[int]] = {}
MEDIAN_LATENCY_DICT:	dict[str, int] = {}
DEPTH_UPDATE_ID_DICT:	dict[str, int] = {}

LATEST_JSON_FLUSH:		dict[str, int] = {}
JSON_FLUSH_INTERVAL:	dict[str, int] = {}

#———————————————————————————————————————————————————————————————————————————————
# EOL: TODO
#———————————————————————————————————————————————————————————————————————————————

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(APP):
	try:
		# Startup logic (if any) goes here
		yield

	except KeyboardInterrupt:
		logger.info(
			f"[{my_name()}] Application terminated by user (Ctrl + C)."
		)

	except Exception as e:
		logger.error(
			f"[{my_name()}] Unhandled exception: {e}", exc_info=True
		)

	finally:

		# Shutdown logic handled by ShutdownManager
		# This ensures no duplicate cleanup

		if 'shutdown_manager' in globals():
			if not shutdown_manager.is_shutdown_complete():
				logger.info(
					f"[{my_name()}] Initiating shutdown via ShutdownManager..."
				)
				shutdown_manager.graceful_shutdown()

		else:
			logger.warning(
				f"[{my_name()}] ShutdownManager not available for cleanup"
			)

APP = FastAPI(lifespan=lifespan)

#———————————————————————————————————————————————————————————————————————————————

@APP.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):

	"""Dashboard HTML 페이지 서빙"""
	try:
		# HTML 파일 경로를 resource_path를 통해 가져오기
		html_path = resource_path(
			"dashboard.html",
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

#———————————————————————————————————————————————————————————————————————————————

from fastapi import WebSocket, WebSocketDisconnect

ACTIVE_DASHBOARD_LOCK		 = asyncio.Lock()
ACTIVE_DASHBOARD_CONNECTIONS = 0

NETWORK_LOAD_MBPS:		int   = 0
CPU_LOAD_PERCENTAGE:	float = 0.0
MEM_LOAD_PERCENTAGE:	float = 0.0
STORAGE_PERCENTAGE:		float = 0.0
GC_TIME_COST_MS:		float = -0.0

#———————————————————————————————————————————————————————————————————————————————

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

#———————————————————————————————————————————————————————————————————————————————
# 🚦 Main Entrypoint & Async Task Orchestration
#———————————————————————————————————————————————————————————————————————————————

if __name__ == "__main__":

	from uvicorn.config import Config
	from uvicorn.server import Server
	import asyncio

	#———————————————————————————————————————————————————————————————————————————
	# THESE TWO MUST BE WITHIN THE MAIN PROCESS
	#———————————————————————————————————————————————————————————————————————————

	MERGE_EXECUTOR = ProcessPoolExecutor(max_workers=len(SYMBOLS))
	ZNR_EXECUTOR   = ProcessPoolExecutor(max_workers=len(SYMBOLS))

	#———————————————————————————————————————————————————————————————————————————
	# SHUTDOWN MANAGER SETUP
	#———————————————————————————————————————————————————————————————————————————

	shutdown_manager = create_shutdown_manager(logger)
	shutdown_manager.register_executors(
		merge=MERGE_EXECUTOR,
		znr=ZNR_EXECUTOR
	)
	shutdown_manager.register_symbols(SYMBOLS)
	shutdown_manager.register_signal_handlers()

	#———————————————————————————————————————————————————————————————————————————

	async def main():

		try:

			(
				EVENT_1ST_SNAPSHOT,
				EVENT_LATENCY_VALID,
				EVENT_STREAM_ENABLE,
			) = init_runtime_state(
				LATENCY_DICT,
				LATENCY_DEQUE_SIZE,
				MEDIAN_LATENCY_DICT,
				DEPTH_UPDATE_ID_DICT,
				LATEST_JSON_FLUSH,
				JSON_FLUSH_INTERVAL,
				SNAPSHOTS_QUEUE_DICT,
				SNAPSHOTS_QUEUE_MAX,
				SYMBOL_TO_FILE_HANDLES,
				RECORDS_MERGED_DATES,
				RECORDS_ZNR_MINUTES,
				SYMBOLS,
				logger,
			)

			shutdown_manager.register_file_handles(
				SYMBOL_TO_FILE_HANDLES
			)
			
			#———————————————————————————————————————————————————————————————————
			# Launch Asynchronous Coroutines
			#———————————————————————————————————————————————————————————————————

			try:

				tasks = [
					asyncio.create_task(
						monitor_hardware(
							NETWORK_LOAD_MBPS,
							CPU_LOAD_PERCENTAGE,
							MEM_LOAD_PERCENTAGE,
							STORAGE_PERCENTAGE,
							HARDWARE_MONITORING_INTERVAL,
							CPU_PERCENT_DURATION,
							DESIRED_MAX_SYS_MEM_LOAD,
							logger,
						)
					),
					asyncio.create_task(
						estimate_latency(
							WS_PING_INTERVAL,
							WS_PING_TIMEOUT,
							DEPTH_UPDATE_ID_DICT,
							LATENCY_DICT,
							LATENCY_SAMPLE_MIN,
							MEDIAN_LATENCY_DICT,
							LATENCY_THRESHOLD_MS,
							EVENT_LATENCY_VALID,
							BASE_BACKOFF,
							MAX_BACKOFF,
							RESET_CYCLE_AFTER,
							RESET_BACKOFF_LEVEL,
							SYMBOLS,
							logger,
						)
					),
					asyncio.create_task(
						gate_streaming_by_latency(
							EVENT_LATENCY_VALID,
							EVENT_STREAM_ENABLE,
							LATENCY_DICT,
							LATENCY_SIGNAL_SLEEP,
							SYMBOLS,
							logger,
						)
					),
					asyncio.create_task(
						put_snapshot(	# @depth20@100ms
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
					),
					*[
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
								MERGE_EXECUTOR,
								RECORDS_MERGED_DATES,
								ZNR_EXECUTOR,
								RECORDS_ZNR_MINUTES,
								RECORDS_MAX,
								logger,
							)
						)
						for symbol in SYMBOLS
					],
				]

			except Exception as e:

				logger.critical(
					f"[{my_name()}] Failed to launch "
					f"async coroutines: {e}",
					exc_info=True
				)
				raise SystemExit from e

			#———————————————————————————————————————————————————————————————————
			# Wait for at least one valid snapshot before serving
			#———————————————————————————————————————————————————————————————————

			try: await EVENT_1ST_SNAPSHOT.wait()
			except Exception as e:

				logger.error(
					f"[{my_name()}] Error while "
					f"waiting for EVENT_1ST_SNAPSHOT: {e}",
					exc_info=True
				)
				raise SystemExit from e

			#———————————————————————————————————————————————————————————————————
			# FastAPI
			#———————————————————————————————————————————————————————————————————

			try:

				logger.info(
					f"[{my_name()}] FastAPI server starts. Try:\n"
					f"\thttp://localhost:8000/orderbook/"
					f"{SYMBOLS[0]}\n"
				)

				cfg = Config(
					app		   = APP,
					host	   = "0.0.0.0",
					port	   = 8000,	# TODO: avoid hardcoding
					lifespan   = "on",
					use_colors = True,
					log_level  = "warning",
					workers	   = os.cpu_count(),
					loop	   = "asyncio",	# TODO: `uvicorn`
				)

				server = Server(cfg)

				await server.serve()

			except Exception as e:

				logger.critical(
					f"[{my_name()}] FastAPI server "
					f"failed to start: {e}",
					exc_info=True
				)
				raise SystemExit from e

		#———————————————————————————————————————————————————————————————————————

		except Exception as e:

			logger.critical(
				f"[{my_name()}] "
				f"Unhandled exception: {e}",
				exc_info=True
			)
			raise SystemExit from e

#———————————————————————————————————————————————————————————————————————————————

	try: asyncio.run(main())

	except KeyboardInterrupt:

		logger.info(
			f"[__main__] Application terminated "
			f"by user (Ctrl + C)."
		)

	except Exception as e:

		logger.critical(
			f"[__main__] Unhandled exception: {e}",
			exc_info=True
		)
		raise SystemExit from e

	finally: pass

"""—————————————————————————————————————————————————————————————————————————————

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

————————————————————————————————————————————————————————————————————————————————

Dashboard URLs:
- http://localhost:8000/dashboard		dev pc
- http://192.168.1.107/dashboard		server (internal access)
- http://c01hyka.duckdns.org/dashboard	server (external access)

—————————————————————————————————————————————————————————————————————————————"""