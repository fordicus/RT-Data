# init.py

#———————————————————————————————————————————————————————————————————————————————

import logging, asyncio
from collections import OrderedDict, deque
from io import TextIOWrapper
from typing import Optional

from util import(
	my_name,
	resource_path,
	get_current_time_ms,
)

from latency import (
	LatencyMonitor,
)

#———————————————————————————————————————————————————————————————————————————————

def setup_uvloop(
	logger:  logging.Logger = None,
	verbose: bool = False,
) -> bool:

	try:

		import uvloop
		asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

		to_prt = f"[{my_name()}]⚡ uvloop"
		if logger:	  logger.info(to_prt)
		elif verbose: print(to_prt, flush = True)

		return True

	except ImportError:

		to_prt = (
			f"[{my_name()}] "
			f"uvloop not available - using default asyncio."
		)
		if logger:	  logger.warning(to_prt)
		elif verbose: print(to_prt, flush = True)
		pass

	except Exception as e:

		to_prt = f"[{my_name()}] Failed to setup uvloop: {e}"
		if logger:	  logger.error(to_prt)
		elif verbose: print(to_prt, flush = True)
		return False

#———————————————————————————————————————————————————————————————————————————————

LAT_MON_SPOT_BINANCE = None

#———————————————————————————————————————————————————————————————————————————————

def load_config(
	logger:		 logging.Logger,
	config_path: str = "app.conf"
) -> tuple[
	#
	list[str],		# symbols
	#
	dict[str, str],	# ws_url
	str,			# wildcard_stream_binance_com_port
	list[str],		# ports_stream_binance_com
	float,			# port_cycling_period_hrs
	float,			# back_up_ready_ahead_sec
	#
	str,			# lob_dir
	str,			# chart_dir
	#
	int,			# purge_on_date_change
	int,			# save_interval_min
	#
	int,			# snapshots_queue_max
	int,			# executions_queue_max
	int,			# records_max
	#
	LatencyMonitor,	# latency measurement & events
	#
	int,			# base_backoff
	int,			# max_backoff
	int, 			# reset_cycle_after
	int,			# reset_backoff_level
	Optional[int],	# ws_ping_interval
	Optional[int],	# ws_ping_timeout
	#
	int,			# dashboard_port_number
	float,			# dashboard_stream_interval
	int,			# max_dashboard_connections
	int,			# max_dashboard_session_sec
	float,			# hardware_monitoring_interval
	float,			# cpu_percent_duration
	float,			# desired_max_sys_mem_load
]:

	#——————————————————————————————————————————————————————————————

	def extract_comma_delimited(
		config: dict[str, str],
		key: str,
	) -> list[str]:

		try:

			val_str = config.get(f"{key}")

			if not isinstance(val_str, str):

				raise ValueError(
					f"[{my_name()}] {key} field "
					f"missing or not a string."
				)

			return list(
				# the input order is preserved
				OrderedDict.fromkeys(
					s.lower()
					for s in val_str.split(",")
					if s.strip()
				)
			)

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to "
				f"extract {key} from {config_path}."
			) from e

	#——————————————————————————————————————————————————————————————

	def extract_symbols(
		config: dict[str, str]
	) -> list[str]:

		try:

			symbols_str = config.get("SYMBOLS")

			if not isinstance(symbols_str, str):

				raise ValueError(
					f"[{my_name()}] SYMBOLS field "
					f"missing or not a string."
				)

			return list(OrderedDict.fromkeys(
				s.lower()
				for s in symbols_str.split(",")
				if s.strip()
			))

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to "
				f"extract symbols from {config_path}."
			) from e

	#——————————————————————————————————————————————————————————————

	def extract_others(
		#
		config:  dict[str, str],
		symbols: list[str],
		#
	) -> tuple[
		str,			# lob_dir
		str,			# chart_dir
		#
		str,			# wildcard_stream_binance_com_port
		float,			# port_cycling_period_hrs
		float,			# back_up_ready_ahead_sec
		#
		int,			# purge_on_date_change
		int,			# save_interval_min
		#
		int,			# snapshots_queue_max
		int,			# executions_queue_max
		int,			# records_max
		#
		int,			# base_backoff
		int,			# max_backoff
		int, 			# reset_cycle_after
		int,			# reset_backoff_level
		#
		Optional[int],	# ws_ping_interval
		Optional[int],	# ws_ping_timeout
		#
		int,			# dashboard_port_number
		float,			# dashboard_stream_interval
		int,			# max_dashboard_connections
		int,			# max_dashboard_session_sec
		float,			# hardware_monitoring_interval
		float,			# cpu_percent_duration
		float,			# desired_max_sys_mem_load
	]:

		global LAT_MON_SPOT_BINANCE

		try:

			lob_dir	  = config.get("LOB_DIR")
			chart_dir = config.get("CHART_DIR")

			wildcard_stream_binance_com_port = config.get(
				"WILDCARD_STREAM_BINANCE_COM_PORT"
			)
			port_cycling_period_hrs = float(config.get(
				"PORT_CYCLING_PERIOD_HRS"
			))
			back_up_ready_ahead_sec = float(config.get(
				"BACK_UP_READY_AHEAD_SEC"
			))

			purge_on_date_change = int(config.get("PURGE_ON_DATE_CHANGE"))
			save_interval_min	 = int(config.get("SAVE_INTERVAL_MIN"))
			if save_interval_min > 1440:
				raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

			snapshots_queue_max	 = int(config.get("SNAPSHOTS_QUEUE_MAX"))
			executions_queue_max = int(config.get("EXECUTIONS_QUEUE_MAX"))
			records_max			 = int(config.get("RECORDS_MAX"))

			LAT_MON_SPOT_BINANCE = LatencyMonitor(
				int(config.get('LATENCY_DEQUE_SIZE')),
				int(config.get('LATENCY_THRESHOLD_MS')),
				float(config.get('LATENCY_ROUTINE_SLEEP_SEC')),
				symbols,
			)

			base_backoff		= int(config.get("BASE_BACKOFF"))
			max_backoff			= int(config.get("MAX_BACKOFF"))
			reset_cycle_after   = int(config.get("RESET_CYCLE_AFTER"))
			reset_backoff_level = int(config.get("RESET_BACKOFF_LEVEL"))

			ws_ping_interval = int(config.get("WS_PING_INTERVAL"))
			ws_ping_timeout  = int(config.get("WS_PING_TIMEOUT"))
			if ws_ping_interval == 0: ws_ping_interval = None
			if ws_ping_timeout  == 0: ws_ping_timeout  = None

			dashboard_port_number		 = int(config.get("DASHBOARD_PORT_NUMBER"))
			dashboard_stream_interval	 = float(config.get("DASHBOARD_STREAM_INTERVAL"))
			max_dashboard_connections	 = int(config.get("MAX_DASHBOARD_CONNECTIONS"))
			max_dashboard_session_sec	 = int(config.get("MAX_DASHBOARD_SESSION_SEC"))
			hardware_monitoring_interval = float(config.get("HARDWARE_MONITORING_INTERVAL"))
			cpu_percent_duration		 = float(config.get("CPU_PERCENT_DURATION"))
			desired_max_sys_mem_load	 = float(config.get("DESIRED_MAX_SYS_MEM_LOAD"))

			return (
				#
				lob_dir,
				chart_dir,
				#
				wildcard_stream_binance_com_port,
				port_cycling_period_hrs,
				back_up_ready_ahead_sec,
				#
				purge_on_date_change,
				save_interval_min,
				#
				snapshots_queue_max,
				executions_queue_max,
				records_max,
				#
				base_backoff,
				max_backoff,
				reset_cycle_after,
				reset_backoff_level,
				#
				ws_ping_interval,
				ws_ping_timeout,
				#
				dashboard_port_number,
				dashboard_stream_interval,
				max_dashboard_connections,
				max_dashboard_session_sec,
				hardware_monitoring_interval,
				cpu_percent_duration,
				desired_max_sys_mem_load
				#
			)

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to "
				f"handle {config_path}."
			) from e

	#——————————————————————————————————————————————————————————————

	try:

		#——————————————————————————————————————————————————————————

		with open(
			resource_path(config_path, logger),
			'r', encoding='utf-8'
		) as f:

			config: dict[str, str] = {}	# loaded from .conf

			for line in f:

				line = line.strip()

				if (
					not line
					or line.startswith("#")
					or "=" not in line
				):
					continue

				line = line.split("#", 1)[0].strip()
				parts = line.split("=", 1)
				if len(parts) != 2:
					continue
				key, val = parts
				config[key.strip()] = val.strip()

		#——————————————————————————————————————————————————————————
		
		symbols = extract_symbols(config)

		#——————————————————————————————————————————————————————————

		(
			#
			lob_dir,
			chart_dir,
			#
			wildcard_stream_binance_com_port,
			port_cycling_period_hrs,
			back_up_ready_ahead_sec,
			#
			purge_on_date_change,
			save_interval_min,
			#
			snapshots_queue_max,
			executions_queue_max,
			records_max,
			#
			base_backoff,
			max_backoff,
			reset_cycle_after,
			reset_backoff_level,
			#
			ws_ping_interval,
			ws_ping_timeout,
			#
			dashboard_port_number,
			dashboard_stream_interval,
			max_dashboard_connections,
			max_dashboard_session_sec,
			hardware_monitoring_interval,
			cpu_percent_duration,
			desired_max_sys_mem_load
			#
		) = extract_others(config, symbols)

		if not symbols:

			raise RuntimeError(
				f"No SYMBOLS loaded from config."
			)

		#———————————————————————————————————————————————————————————————————————
		# https://tinyurl.com/BinanceWsMan
		#———————————————————————————————————————————————————————————————————————
		# [2025-08-05] The base endpoint is: 
		# 	wss://stream.binance.com:9443 or
		# 	wss://stream.binance.com:443.
		#———————————————————————————————————————————————————————————————————————

		ws_url = {}

		ws_url[
			'STREAM_BINANCE_COM_DEPTH20_100MS'
		] = (
			f"wss://stream.binance.com:{wildcard_stream_binance_com_port}"
			f"/stream?streams="
			f"{'/'.join(f'{sym}@depth20@100ms' for sym in symbols)}"
		)

		ws_url[
			'STREAM_BINANCE_COM_AGGTRADE'
		] = (
			f"wss://stream.binance.com:{wildcard_stream_binance_com_port}"
			f"/stream?streams="
			f"{'/'.join(f'{sym}@aggTrade' for sym in symbols)}"
		)

		#———————————————————————————————————————————————————————————————————————

		ports_stream_binance_com = extract_comma_delimited(
			config, "PORTS_STREAM_BINANCE_COM",
		)

		#———————————————————————————————————————————————————————————————————————

		return (
			symbols,
			#
			ws_url,
			wildcard_stream_binance_com_port,
			ports_stream_binance_com,
			port_cycling_period_hrs,
			back_up_ready_ahead_sec,
			#
			lob_dir,
			chart_dir,
			#
			purge_on_date_change,
			save_interval_min,
			#
			snapshots_queue_max,
			executions_queue_max,
			records_max,
			#
			LAT_MON_SPOT_BINANCE,
			#
			base_backoff,
			max_backoff,
			reset_cycle_after,
			reset_backoff_level,
			#
			ws_ping_interval, ws_ping_timeout,
			#
			dashboard_port_number,
			dashboard_stream_interval,
			max_dashboard_connections,
			max_dashboard_session_sec,
			hardware_monitoring_interval,
			cpu_percent_duration,
			desired_max_sys_mem_load
			#
		)

	except Exception as e:

		logger.critical(
			f"[{my_name()}] Failed to load config: "
			f"{e}", exc_info=True
		)
		raise SystemExit

#———————————————————————————————————————————————————————————————————————————————

def init_runtime_state(
	#———————————————————————————————————————————————————————————————————————————
	lob_sav_intv_spot_binance:	dict[str, deque[int]],
	exe_sav_intv_spot_binance:	dict[str, deque[int]],
	#———————————————————————————————————————————————————————————————————————————
	put_snapshot_interval:		dict[str, deque[int]],
	#———————————————————————————————————————————————————————————————————————————
	snapshots_queue_dict:		dict[str, asyncio.Queue],
	snapshots_queue_max:		int,
	#———————————————————————————————————————————————————————————————————————————
	executions_queue_dict:		dict[str, asyncio.Queue],
	executions_queue_max:		int,
	#———————————————————————————————————————————————————————————————————————————
	fhndls_lob_spot_binance:	dict[str, tuple[str, TextIOWrapper]],
	fhndls_exe_spot_binance:	dict[str, tuple[str, TextIOWrapper]],
	#———————————————————————————————————————————————————————————————————————————
	symbols:					list[str],
	logger:						logging.Logger,
	#———————————————————————————————————————————————————————————————————————————
	monitoring_deque_len:		int = 100,
	#———————————————————————————————————————————————————————————————————————————
):

	try:

		#———————————————————————————————————————————————————————————————————————

		lob_sav_intv_spot_binance.clear()
		lob_sav_intv_spot_binance.update({
			symbol: deque(
				maxlen = monitoring_deque_len
			)
			for symbol in symbols
		})

		exe_sav_intv_spot_binance.clear()
		exe_sav_intv_spot_binance.update({
			symbol: deque(
				maxlen = monitoring_deque_len
			)
			for symbol in symbols
		})

		#———————————————————————————————————————————————————————————————————————

		put_snapshot_interval.clear()
		put_snapshot_interval.update({
			symbol: deque(maxlen = monitoring_deque_len)
			for symbol in symbols
		})

		snapshots_queue_dict.clear()
		snapshots_queue_dict.update({
			symbol: asyncio.Queue(
				maxsize = snapshots_queue_max
			)
			for symbol in symbols
		})

		executions_queue_dict.clear()
		executions_queue_dict.update({
			symbol: asyncio.Queue(
				maxsize = executions_queue_max
			)
			for symbol in symbols
		})

		#———————————————————————————————————————————————————————————————————————

		fhndls_lob_spot_binance.clear()
		fhndls_exe_spot_binance.clear()

		#———————————————————————————————————————————————————————————————————————

		logger.info(
			f"[{my_name()}]📦 runtime ready"
		)

		#———————————————————————————————————————————————————————————————————————

	except Exception as e:

		logger.error(
			f"[{my_name()}] Failed to "
			f"initialize runtime state: {e}",
			exc_info=True
		)
		raise SystemExit from e

#———————————————————————————————————————————————————————————————————————————————