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
	create_shutdown_callback,
)

from hotswap import (
	HotSwapManager,
)

from core import (
	put_snapshot,
	symbol_dump_snapshot,
)

from exec import (
	put_execution,
	symbol_dump_execution,
)

from latency import (
	gate_streaming_by_latency,
	estimate_latency,
)

from dashboard import (
	monitor_hardware,
	create_dashboard_server,
)

from util import (
	my_name,
	resource_path,
	get_cur_datetime_str,
	update_shared_time_dict,
	format_ws_url,
	set_global_logger,
	get_ssl_context,
)

import os, signal, threading, time, random, logging
import asyncio, certifi
from datetime import datetime, timezone
from collections import deque
from io import TextIOWrapper
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor

#———————————————————————————————————————————————————————————————————————————————

# os.environ["SSL_CERT_FILE"] = certifi.where()
get_ssl_context()

logger, queue_listener = set_global_logger()

setup_uvloop(logger = logger)

#———————————————————————————————————————————————————————————————————————————————

(
	SYMBOLS,
	#
	WS_URL,
	WILDCARD_STREAM_BINANCE_COM_PORT,
	PORTS_STREAM_BINANCE_COM,
	PORT_CYCLING_PERIOD_HRS,
	BACK_UP_READY_AHEAD_SEC,
	#
	LOB_DIR,
	CHART_DIR,
	#
	PURGE_ON_DATE_CHANGE, SAVE_INTERVAL_MIN,
	#
	SNAPSHOTS_QUEUE_MAX, RECORDS_MAX,
	#
	LATENCY_DEQUE_SIZE, LATENCY_SAMPLE_MIN,
	LATENCY_THRESHOLD_MS, LATENCY_ROUTINE_SLEEP_SEC,
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
# GLOBAL ARRAYS
#———————————————————————————————————————————————————————————————————————————————

SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}
EXECUTIONS_QUEUE_DICT:		dict[str, asyncio.Queue] = {}

FHNDLS_LOB_SPOT_BINANCE:	dict[str, tuple[str, TextIOWrapper]] = {}
FHNDLS_EXE_SPOT_BINANCE:	dict[str, tuple[str, TextIOWrapper]] = {}

SHARED_TIME_DICT:			dict[str, float] = {}

#———————————————————————————————————————————————————————————————————————————————

LOB_SAV_INTV_SPOT_BINANCE:	dict[str, deque[int]] = {}
EXE_SAV_INTV_SPOT_BINANCE:	dict[str, deque[int]] = {}		# minimal monitoring

PUT_SNAPSHOT_INTERVAL:		dict[str, deque[int]] = {}
MEAN_LATENCY_DICT:			dict[str, int] = {}
WEBSOCKET_PEER:				dict[str, str] = {"value": "UNKNOWN"}

#———————————————————————————————————————————————————————————————————————————————

if __name__ == "__main__":

	from uvicorn.config import Config
	from uvicorn.server import Server

	#———————————————————————————————————————————————————————————————————————————
	# THESE TWO MUST BE WITHIN THE MAIN PROCESS
	#———————————————————————————————————————————————————————————————————————————

	LOB_MERGE_EXC_SPOT_BINANCE = ProcessPoolExecutor(max_workers = len(SYMBOLS))
	EXE_MERGE_EXC_SPOT_BINANCE = ProcessPoolExecutor(max_workers = len(SYMBOLS))

	LOB_ZNR_EXC_SPOT_BINANCE   = ProcessPoolExecutor(max_workers = len(SYMBOLS))
	EXE_ZNR_EXC_SPOT_BINANCE   = ProcessPoolExecutor(max_workers = len(SYMBOLS))

	#———————————————————————————————————————————————————————————————————————————
	# SHUTDOWN MANAGER SETUP
	#———————————————————————————————————————————————————————————————————————————

	(
		SHUTDOWN_MANAGER,
		MAIN_SHUTDOWN_EVENT,
	) = create_shutdown_manager(logger)

	SHUTDOWN_MANAGER.register_executors(
		#———————————————————————————————————————————————————————————————————————
		lob_merge_exc_spot_binance = LOB_MERGE_EXC_SPOT_BINANCE,
		exe_merge_exc_spot_binance = EXE_MERGE_EXC_SPOT_BINANCE,
		#———————————————————————————————————————————————————————————————————————
		lob_znr_exc_spot_binance   = LOB_ZNR_EXC_SPOT_BINANCE,
		exe_znr_exc_spot_binance   = EXE_ZNR_EXC_SPOT_BINANCE,
		#———————————————————————————————————————————————————————————————————————
	)
	SHUTDOWN_MANAGER.register_symbols(SYMBOLS)
	SHUTDOWN_MANAGER.register_signal_handlers()

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
				#———————————————————————————————————————————————————————————————
				MEAN_LATENCY_DICT,
				LOB_SAV_INTV_SPOT_BINANCE,
				EXE_SAV_INTV_SPOT_BINANCE,
				#———————————————————————————————————————————————————————————————
				PUT_SNAPSHOT_INTERVAL,
				#———————————————————————————————————————————————————————————————
				SNAPSHOTS_QUEUE_DICT,
				SNAPSHOTS_QUEUE_MAX,
				EXECUTIONS_QUEUE_DICT,
				#———————————————————————————————————————————————————————————————
				FHNDLS_LOB_SPOT_BINANCE,
				FHNDLS_EXE_SPOT_BINANCE,
				#———————————————————————————————————————————————————————————————
				SYMBOLS,
				logger,
				#———————————————————————————————————————————————————————————————
			#
			)

			#———————————————————————————————————————————————————————————————————
			#	list[
			#		dict[str, tuple[str, TextIOWrapper]]
			#	]
			#———————————————————————————————————————————————————————————————————

			SHUTDOWN_MANAGER.register_file_handles(
				[
					FHNDLS_LOB_SPOT_BINANCE,
					FHNDLS_EXE_SPOT_BINANCE,
				]
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
				'SNAPSHOTS_QUEUE_DICT':  SNAPSHOTS_QUEUE_DICT,					# TBA
				'MEAN_LATENCY_DICT':	 MEAN_LATENCY_DICT,
				'JSON_FLUSH_INTERVAL':   LOB_SAV_INTV_SPOT_BINANCE,				# NAME MISMATCH
				'PUT_SNAPSHOT_INTERVAL': PUT_SNAPSHOT_INTERVAL,
			}
			
			dashboard_server = create_dashboard_server(
				state_refs =	   dashboard_state,
				config =		   dashboard_config,
				shutdown_manager = SHUTDOWN_MANAGER,
				logger =		   logger,
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
					name = "estimate_latency()",
				)

				#———————————————————————————————————————————————————————————————
				# Websocket (re)connection attempt requires at minimum 1.0s
				# after each trial (https://tinyurl.com/BinanceWsMan);
				# exponential backoff unnecessary
				#———————————————————————————————————————————————————————————————

				update_shared_time_dict(SHARED_TIME_DICT,
					'LATEST_SLEEP_TIME_BINANCE_STREAM',
				)

				#———————————————————————————————————————————————————————————————
				# put_snapshot @core.py
				#———————————————————————————————————————————————————————————————
				
				HSM_PUT_SNAPSHOT_BINANCE_DEPTH20_100MS = HotSwapManager(
					name = "put_snapshot_binance_depth20_100ms",
					shutdown_event = MAIN_SHUTDOWN_EVENT,
				)

				put_snapshot_task = asyncio.create_task(
					put_snapshot(								# @depth20@100ms
						#———————————————————————————————————————————————————————
						PUT_SNAPSHOT_INTERVAL,
						#———————————————————————————————————————————————————————
						SNAPSHOTS_QUEUE_DICT,
						#———————————————————————————————————————————————————————
						EVENT_STREAM_ENABLE,
						MEAN_LATENCY_DICT,
						EVENT_1ST_SNAPSHOT,
						#———————————————————————————————————————————————————————
						SHARED_TIME_DICT,
						'LATEST_SLEEP_TIME_BINANCE_STREAM',
						1.5,		# `sleep_on_ws_reconn`
						#———————————————————————————————————————————————————————
						WS_URL, 'STREAM_BINANCE_COM_DEPTH20_100MS',
						WILDCARD_STREAM_BINANCE_COM_PORT,
						PORTS_STREAM_BINANCE_COM,
						#———————————————————————————————————————————————————————
						WS_PING_INTERVAL, WS_PING_TIMEOUT,
						SYMBOLS, logger,
						#———————————————————————————————————————————————————————
						port_cycling_period_hrs = PORT_CYCLING_PERIOD_HRS,
						back_up_ready_ahead_sec = BACK_UP_READY_AHEAD_SEC,
						hotswap_manager = HSM_PUT_SNAPSHOT_BINANCE_DEPTH20_100MS,
						shutdown_event	= MAIN_SHUTDOWN_EVENT,
						handoff_event	= None,
						is_backup		= False,
						#———————————————————————————————————————————————————————
					),
					name = f"put_snapshot() @{get_cur_datetime_str()}",
				)

				HSM_PUT_SNAPSHOT_BINANCE_DEPTH20_100MS.\
					append_task_w_creation_time(
						put_snapshot_task,
					)

				#———————————————————————————————————————————————————————————————
				# put_execution @exec.py
				#———————————————————————————————————————————————————————————————

				HSM_PUT_EXECUTION_BINANCE_AGGTRADE = HotSwapManager(
					name = "put_execution_binance_aggtrade",
					shutdown_event = MAIN_SHUTDOWN_EVENT,
				)

				put_execution_task = asyncio.create_task(
					put_execution(									# @aggTrade
						#———————————————————————————————————————————————————————
						EXECUTIONS_QUEUE_DICT,
						#———————————————————————————————————————————————————————
						EVENT_STREAM_ENABLE,
						MEAN_LATENCY_DICT,
						EVENT_1ST_SNAPSHOT,
						#———————————————————————————————————————————————————————
						SHARED_TIME_DICT,
						'LATEST_SLEEP_TIME_BINANCE_STREAM',
						1.5,		# `sleep_on_ws_reconn`
						#———————————————————————————————————————————————————————
						WS_URL, 'STREAM_BINANCE_COM_AGGTRADE',
						WILDCARD_STREAM_BINANCE_COM_PORT,
						PORTS_STREAM_BINANCE_COM,
						#———————————————————————————————————————————————————————
						WS_PING_INTERVAL, WS_PING_TIMEOUT,
						SYMBOLS, logger,
						#———————————————————————————————————————————————————————
						port_cycling_period_hrs = PORT_CYCLING_PERIOD_HRS,
						back_up_ready_ahead_sec = BACK_UP_READY_AHEAD_SEC,
						hotswap_manager = HSM_PUT_EXECUTION_BINANCE_AGGTRADE,
						shutdown_event	= MAIN_SHUTDOWN_EVENT,
						handoff_event	= None,
						is_backup		= False,
						#———————————————————————————————————————————————————————
					),
					name = f"put_execution() @{get_cur_datetime_str()}",
				)
				
				HSM_PUT_EXECUTION_BINANCE_AGGTRADE.\
					append_task_w_creation_time(
						put_execution_task,
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
					name = "monitor_hardware()",
				)

				#———————————————————————————————————————————————————————————————
				# symbol_dump_snapshot @core.py
				#———————————————————————————————————————————————————————————————

				for symbol in SYMBOLS:
					task = asyncio.create_task(
						symbol_dump_snapshot(
							symbol,
							SAVE_INTERVAL_MIN,
							SNAPSHOTS_QUEUE_DICT,
							LOB_DIR,
							FHNDLS_LOB_SPOT_BINANCE,
							LOB_SAV_INTV_SPOT_BINANCE,		# monitoring
							PURGE_ON_DATE_CHANGE,
							LOB_MERGE_EXC_SPOT_BINANCE,		# fire-and-forget
							LOB_ZNR_EXC_SPOT_BINANCE,		# fire-and-forget
							RECORDS_MAX,
							logger,
							MAIN_SHUTDOWN_EVENT,
						),
						name = f"symbol_dump_snapshot({symbol})",
					)

				#———————————————————————————————————————————————————————————————
				# symbol_dump_execution @core.py
				#———————————————————————————————————————————————————————————————

				for symbol in SYMBOLS:
					task = asyncio.create_task(
						symbol_dump_execution(
							symbol,
							SAVE_INTERVAL_MIN,
							EXECUTIONS_QUEUE_DICT,
							CHART_DIR,
							FHNDLS_EXE_SPOT_BINANCE,
							EXE_SAV_INTV_SPOT_BINANCE,		# monitoring
							PURGE_ON_DATE_CHANGE,
							EXE_MERGE_EXC_SPOT_BINANCE,		# fire-and-forget
							EXE_ZNR_EXC_SPOT_BINANCE,		# fire-and-forget
							RECORDS_MAX,
							logger,
							MAIN_SHUTDOWN_EVENT,
						),
						name = f"symbol_dump_execution({symbol})",
					)

				#———————————————————————————————————————————————————————————————

				gate_streaming_by_latency_task = asyncio.create_task(
					gate_streaming_by_latency(
						EVENT_LATENCY_VALID,
						EVENT_STREAM_ENABLE,
						MEAN_LATENCY_DICT,
						LATENCY_ROUTINE_SLEEP_SEC,
						SYMBOLS,
						logger,
						shutdown_event = MAIN_SHUTDOWN_EVENT,
					),
					name = "gate_streaming_by_latency()",
				)

				#———————————————————————————————————————————————————————————————
				# Cleanup Callback for HotSwapManaters
				#———————————————————————————————————————————————————————————————

				SHUTDOWN_MANAGER.add_cleanup_callback(
					create_shutdown_callback(
						hotswap_manager  = HSM_PUT_SNAPSHOT_BINANCE_DEPTH20_100MS,
						shutdown_manager = SHUTDOWN_MANAGER,
						logger			 = logger,
					)
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
					app		  			   = dashboard_server.app,
					host	  			   = "0.0.0.0",
					port	  			   = DASHBOARD_PORT_NUMBER,
					lifespan  			   = "on",
					use_colors			   = True,
					log_level 			   = "warning",
					workers	  			   = 1,
					loop	  			   = "asyncio",
					ws_per_message_deflate = False,
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
				SHUTDOWN_MANAGER
				and not SHUTDOWN_MANAGER.is_shutdown_complete()
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
			SHUTDOWN_MANAGER
			and not SHUTDOWN_MANAGER.is_shutdown_complete()
		):
			
			SHUTDOWN_MANAGER.graceful_shutdown()
			
#———————————————————————————————————————————————————————————————————————————————