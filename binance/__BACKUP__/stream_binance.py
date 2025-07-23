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
	python==3.11.13
	pyinstaller==6.14.2
	pyinstaller-hooks-contrib==2025.7
	websockets==15.0.1
	fastapi==0.116.1
	uvicorn==0.35.0
	psutil==7.0.0
	memray==1.17.2

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
	create_dashboard_server,
)

import os, time, random, logging
import asyncio, certifi
from datetime import datetime, timezone
from collections import deque
from io import TextIOWrapper
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor

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

#———————————————————————————————————————————————————————————————————————————————-

SNAPSHOTS_QUEUE_DICT:   dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]] = {}

RECORDS_MERGED_DATES:	dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:	dict[str, OrderedDict[str]] = {}

PUT_SNAPSHOT_INTERVAL:	dict[str, deque[int]] = {}
MEDIAN_LATENCY_DICT:	dict[str, int] = {}

LATEST_JSON_FLUSH:		dict[str, int] = {}
JSON_FLUSH_INTERVAL:	dict[str, deque[int]] = {}

#———————————————————————————————————————————————————————————————————————————————-

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

			#———————————————————————————————————————————————————————————————————

			(
				EVENT_1ST_SNAPSHOT,
				EVENT_LATENCY_VALID,
				EVENT_STREAM_ENABLE,
			) = init_runtime_state(
				MEDIAN_LATENCY_DICT,
				LATEST_JSON_FLUSH,
				JSON_FLUSH_INTERVAL,
				PUT_SNAPSHOT_INTERVAL,
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
			# 대시보드 서버 설정
			#———————————————————————————————————————————————————————————————————
			
			dashboard_config = {
				'DASHBOARD_STREAM_INTERVAL': DASHBOARD_STREAM_INTERVAL,
				'MAX_DASHBOARD_CONNECTIONS': MAX_DASHBOARD_CONNECTIONS,
				'MAX_DASHBOARD_SESSION_SEC': MAX_DASHBOARD_SESSION_SEC,
				'BASE_BACKOFF':				 BASE_BACKOFF,
				'MAX_BACKOFF':				 MAX_BACKOFF,
				'RESET_CYCLE_AFTER':		 RESET_CYCLE_AFTER,
				'RESET_BACKOFF_LEVEL':		 RESET_BACKOFF_LEVEL,
			}
			
			dashboard_state = {
				'SYMBOLS': SYMBOLS,
				'SNAPSHOTS_QUEUE_DICT':  SNAPSHOTS_QUEUE_DICT,
				'MEDIAN_LATENCY_DICT':   MEDIAN_LATENCY_DICT,
				'JSON_FLUSH_INTERVAL':   JSON_FLUSH_INTERVAL,
				'PUT_SNAPSHOT_INTERVAL': PUT_SNAPSHOT_INTERVAL,
			}
			
			dashboard_server = create_dashboard_server(
				state_refs=dashboard_state,
				config=dashboard_config,
				shutdown_manager=shutdown_manager,
				logger=logger
			)
			
			#———————————————————————————————————————————————————————————————————
			# Launch Asynchronous Coroutines
			#———————————————————————————————————————————————————————————————————

			try:

				tasks = [
					asyncio.create_task(
						monitor_hardware(
							dashboard_server,
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
							LATENCY_DEQUE_SIZE,
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
							MEDIAN_LATENCY_DICT,
							LATENCY_SIGNAL_SLEEP,
							SYMBOLS,
							logger,
						)
					),
					asyncio.create_task(
						put_snapshot(	# @depth20@100ms
							PUT_SNAPSHOT_INTERVAL,
							SNAPSHOTS_QUEUE_DICT,
							EVENT_STREAM_ENABLE,
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
					f"\thttp://localhost:8000/dashboard\n"
				)

				cfg = Config(
					app=dashboard_server.app,  # 변경: APP → dashboard_server.app
					host="0.0.0.0",
					port=8000,
					lifespan="on",
					use_colors=True,
					log_level="warning",
					workers=os.cpu_count(),
					loop="asyncio",
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

#———————————————————————————————————————————————————————————————————————————————