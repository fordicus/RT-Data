# stream_binance.py

r"""————————————————————————————————————————————————————————————————————————————

BinanceWsMan:

	https://tinyurl.com/BinanceWsMan

Binance websocket:

	wss://stream.binance.com:{9443|443}/stream?
		streams={symbol}@depth20@100ms

————————————————————————————————————————————————————————————————————————————————

How to Run:

	sudo chrt -f 80 nice -n -19 ionice -c1 -n0 $(which python) stream_binance.py

————————————————————————————————————————————————————————————————————————————————

Dependency:

	python==3.11.13
	aiohttp==3.12.14
	fastapi==0.116.1
	pyinstaller==6.12.0
	orjson==3.11.0
	psutil==7.0.0
	uvicorn==0.35.0
	websockets==15.0.1
	numpy==2.3.2
	uvloop==0.21.0
	memray==1.17.2

	conda list | egrep '^(uvloop|websockets|aiohttp|orjson|fastapi|uvicorn|psutil|pyinstaller|memray)[[:space:]]+'

Note:

	`msgspec` could have replaced `orjson`, but based on our tests, the switch
	was deemed unnecessary. Similarly, `aiofiles` was not utilized for the same
	reason. Finally, we prefer compatibility in compression format, sticking to
	the standard `.zip` algorithm.
	
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

—————————————————————————————————————————————————————————————————————————————"""

from init import (
	setup_uvloop,
	load_config,
	init_runtime_state,
)

from shutdown import (
	ShutdownManager,
	create_shutdown_manager,
)

from util import (
	my_name,
	resource_path,
	get_current_time_ms,
	ms_to_datetime,
	format_ws_url,
	set_global_logger,
)

from hotswap import (
	HotSwapManager,
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

import os, signal, threading, time, random, logging
import asyncio, certifi
from datetime import datetime, timezone
from collections import deque
from io import TextIOWrapper
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor

#———————————————————————————————————————————————————————————————————————————————

os.environ["SSL_CERT_FILE"] = certifi.where()

logger, queue_listener = set_global_logger()

setup_uvloop(logger = logger)

#———————————————————————————————————————————————————————————————————————————————

(
	SYMBOLS,
	#
	WS_URL,
	WILDCARD_STREAM_BINANCE_COM_PORT,
	PORTS_STREAM_BINANCE_COM,
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
	DASHBOARD_PORT_NUMBER,
	DASHBOARD_STREAM_INTERVAL,
	MAX_DASHBOARD_CONNECTIONS,
	MAX_DASHBOARD_SESSION_SEC,
	HARDWARE_MONITORING_INTERVAL,
	CPU_PERCENT_DURATION,
	DESIRED_MAX_SYS_MEM_LOAD
	#
) = load_config(logger)

#———————————————————————————————————————————————————————————————————————————————

SNAPSHOTS_QUEUE_DICT:	  dict[str, asyncio.Queue] = {}
SYMBOL_TO_FILE_HANDLES:	  dict[str, tuple[str, TextIOWrapper]] = {}

RECORDS_MERGED_DATES:	  dict[str, OrderedDict[str]] = {}
RECORDS_ZNR_MINUTES:	  dict[str, OrderedDict[str]] = {}

PUT_SNAPSHOT_INTERVAL:	  dict[str, deque[int]] = {}
MEAN_LATENCY_DICT:		  dict[str, int] = {}

LATEST_JSON_FLUSH:		  dict[str, int] = {}
JSON_FLUSH_INTERVAL:	  dict[str, deque[int]] = {}

WEBSOCKET_PEER:			  dict[str, str]   = {"value": "UNKNOWN"}
WEBSOCKET_RECV_INTV_STAT: dict[str, float] = {"p90": float('inf')}
WEBSOCKET_RECV_INTERVAL:  deque[float] = deque(
	maxlen = max(len(SYMBOLS), 300)
)

#———————————————————————————————————————————————————————————————————————————————

#———————————————————————————————————————————————————————————————————————————————

if __name__ == "__main__":

	from uvicorn.config import Config
	from uvicorn.server import Server

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
			#
				EVENT_1ST_SNAPSHOT,
				EVENT_LATENCY_VALID,
				EVENT_STREAM_ENABLE,
			#
			) = init_runtime_state(
			#
				MEAN_LATENCY_DICT,
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
			#
			)

			shutdown_manager.register_file_handles(
				SYMBOL_TO_FILE_HANDLES
			)

			#———————————————————————————————————————————————————————————————————

			MAIN_SHUTDOWN_EVENT = asyncio.Event()

			shutdown_manager.register_shutdown_event(
				MAIN_SHUTDOWN_EVENT
			)

			#———————————————————————————————————————————————————————————————————
			# Dashboard Endpoint Configuration
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
				'SYMBOLS':				 SYMBOLS,
				'WEBSOCKET_PEER':		 WEBSOCKET_PEER,
				'SNAPSHOTS_QUEUE_DICT':  SNAPSHOTS_QUEUE_DICT,
				'MEAN_LATENCY_DICT':	 MEAN_LATENCY_DICT,
				'JSON_FLUSH_INTERVAL':   JSON_FLUSH_INTERVAL,
				'PUT_SNAPSHOT_INTERVAL': PUT_SNAPSHOT_INTERVAL,
			}
			
			dashboard_server = create_dashboard_server(
				state_refs =	   dashboard_state,
				config =		   dashboard_config,
				shutdown_manager = shutdown_manager,
				logger =		   logger
			)
			
			#———————————————————————————————————————————————————————————————————
			# Launch Asynchronous Coroutines
			#———————————————————————————————————————————————————————————————————

			try:

				estimate_latency_task = asyncio.create_task(
					estimate_latency(
						WEBSOCKET_PEER,
						WS_PING_INTERVAL,
						WS_PING_TIMEOUT,
						LATENCY_DEQUE_SIZE,
						LATENCY_SAMPLE_MIN,
						MEAN_LATENCY_DICT,
						LATENCY_THRESHOLD_MS,
						EVENT_LATENCY_VALID,
						BASE_BACKOFF,
						MAX_BACKOFF,
						RESET_CYCLE_AFTER,
						RESET_BACKOFF_LEVEL,
						SYMBOLS,
						logger,
						shutdown_event = MAIN_SHUTDOWN_EVENT,
					), 
					name="estimate_latency()",
				)

				#———————————————————————————————————————————————————————————————
				
				HOTSWAP_MANAGER = HotSwapManager()
				HOTSWAP_MANAGER.set_shutdown_event(
					MAIN_SHUTDOWN_EVENT
				)

				#———————————————————————————————————————————————————————————————

				put_snapshot_task = asyncio.create_task(
					put_snapshot(	# @depth20@100ms
						#
						WEBSOCKET_RECV_INTERVAL,
						WEBSOCKET_RECV_INTV_STAT,
						PUT_SNAPSHOT_INTERVAL,
						#
						SNAPSHOTS_QUEUE_DICT,
						#
						EVENT_STREAM_ENABLE,
						MEAN_LATENCY_DICT,
						EVENT_1ST_SNAPSHOT,
						#
						MAX_BACKOFF, 
						BASE_BACKOFF,
						RESET_CYCLE_AFTER,
						RESET_BACKOFF_LEVEL,
						#
						WS_URL,
						WILDCARD_STREAM_BINANCE_COM_PORT,
						PORTS_STREAM_BINANCE_COM,
						#
						WS_PING_INTERVAL,
						WS_PING_TIMEOUT,
						SYMBOLS,
						logger,
						#
						# port_cycling_period_hours =  12.0,		# 12 hours
						port_cycling_period_hours =   1.0,		# 60 minutes
						# port_cycling_period_hours =   0.5,		# 30 minutes
						# port_cycling_period_hours =   0.016667,	# 60 seconds
						# port_cycling_period_hours =   0.008333, # 30 seconds
						back_up_ready_ahead_sec = 60.0,
						# back_up_ready_ahead_sec = 10.0,
						# back_up_ready_ahead_sec =  7.5,
						# back_up_ready_ahead_sec =  5.0,
						hotswap_manager =	HOTSWAP_MANAGER,
						shutdown_event =	MAIN_SHUTDOWN_EVENT,	# 실제 연동된 이벤트
						handoff_event =		None,					# 메인 연결
						is_backup =			False,
					),
					name="put_snapshot()",
				)

				#———————————————————————————————————————————————————————————————

				monitor_hardware_task = asyncio.create_task(
					monitor_hardware(
						dashboard_server,
						HARDWARE_MONITORING_INTERVAL,
						CPU_PERCENT_DURATION,
						DESIRED_MAX_SYS_MEM_LOAD,
						logger,
					),
					name="monitor_hardware()",
				)

				#———————————————————————————————————————————————————————————————

				dump_tasks = []
				for symbol in SYMBOLS:
					task = asyncio.create_task(
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
							shutdown_event = MAIN_SHUTDOWN_EVENT,
						),
						name=f"symbol_dump_snapshot({symbol})"
					)
					dump_tasks.append(task)

				#———————————————————————————————————————————————————————————————

				gate_streaming_by_latency_task = asyncio.create_task(
					gate_streaming_by_latency(
						EVENT_LATENCY_VALID,
						EVENT_STREAM_ENABLE,
						MEAN_LATENCY_DICT,
						LATENCY_SIGNAL_SLEEP,
						SYMBOLS,
						logger,
						shutdown_event = MAIN_SHUTDOWN_EVENT,
					),
					name="gate_streaming_by_latency()",
				)

				#———————————————————————————————————————————————————————————————

				all_tasks = [
					estimate_latency_task,
					put_snapshot_task,
					monitor_hardware_task,
					*dump_tasks,
					gate_streaming_by_latency_task,
				]

				#———————————————————————————————————————————————————————————————

				def shutdown_callback():

					#———————————————————————————————————————————————————————————

					async def wait_and_print_final(
						shutdown_manager:	ShutdownManager,
						cleanup_task:		asyncio.Task,
						logger:				logging.Logger,
					):

						try:

							await cleanup_task

						except Exception as e:

							logger.error(
								f"[{my_name()}] "
								f"Hotswap cleanup error: {e}"
							)

						finally:

							shutdown_manager.final_message()

					#———————————————————————————————————————————————————————————

					logger.info(
						f"[{my_name()}] HOTSWAP_MANAGER @main"
					)

					if HOTSWAP_MANAGER:

						try:

							loop = asyncio.get_running_loop()

							if loop and not loop.is_closed():

								cleanup_task = loop.create_task(
									HOTSWAP_MANAGER.graceful_shutdown(logger)
								)
								
								asyncio.create_task(
									wait_and_print_final(
										shutdown_manager,
										cleanup_task,
										logger,
									)
								)

						except Exception as e:

							logger.error(
								f"[{my_name()}] HOTSWAP_MANAGER: {e}"
							)
							
							shutdown_manager.final_message()
					else:
						
						shutdown_manager.final_message()

				#———————————————————————————————————————————————————————————————

				shutdown_manager.add_cleanup_callback(
					shutdown_callback
				)

				#———————————————————————————————————————————————————————————————

			except Exception as e:

				logger.critical(
					f"[{my_name()}] failed to launch "
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
					f"[{my_name()}] error while "
					f"waiting for EVENT_1ST_SNAPSHOT: {e}",
					exc_info=True
				)
				raise SystemExit from e

			#———————————————————————————————————————————————————————————————————
			# FastAPI
			#———————————————————————————————————————————————————————————————————

			try:

				cfg = Config(
					app		   = dashboard_server.app,
					host	   = "0.0.0.0",
					port	   = DASHBOARD_PORT_NUMBER,
					lifespan   = "on",
					use_colors = True,
					log_level  = "warning",
					workers	   = 1,
					loop	   = "asyncio",
				)

				server = Server(cfg)
				logger.info(
					f"[{my_name()}]🚀 fastapi starts → "
					f"http://localhost:{DASHBOARD_PORT_NUMBER}/dashboard"
				)
				await server.serve()
				logger.info(
					f"[{my_name()}]⚓ fastapi ends"
				)

			except Exception as e:

				logger.critical(
					f"[{my_name()}] fastapi "
					f"failed to start: {e}",
					exc_info=True
				)
				raise SystemExit from e

		#———————————————————————————————————————————————————————————————————————

		except Exception as e:

			logger.critical(
				f"[{my_name()}] "
				f"unhandled exception: {e}",
				exc_info=True
			)
			raise SystemExit from e

#———————————————————————————————————————————————————————————————————————————————

	try: asyncio.run(main())

	except KeyboardInterrupt:

		logger.info(
			f"[{my_name()}] application terminated "
			f"by user (Ctrl + C)."
		)

	except Exception as e:

		logger.critical(
			f"[{my_name()}] unhandled exception: {e}",
			exc_info=True
		)
		raise SystemExit from e

	finally:

		try: queue_listener.stop()
		except Exception: pass

		def conditional_force_exit(
			patience_sec: float = 10.0
		):

			time.sleep(patience_sec)

			if (
				shutdown_manager
				and not shutdown_manager.is_shutdown_complete()
			):

				logger.warning(
					f"[{my_name()}] "
					f"shutdown incomplete: "
					f"forcing exit"
				)

				try:

					for handler in logger.handlers:

						handler.flush()

					os.kill(os.getpid(), signal.SIGKILL)

				except Exception:

					os._exit(1)

		threading.Thread(
			target=conditional_force_exit,
			daemon=True
		).start()

		if (
			shutdown_manager
			and not shutdown_manager.is_shutdown_complete()
		):
			
			shutdown_manager.graceful_shutdown()
			
#———————————————————————————————————————————————————————————————————————————————