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

#———————————————————————————————————————————————————————————————————————————————

def load_config(
	logger: logging.Logger,
	config_path: str = "app.conf"
) -> tuple[
	list[str],		# symbols
	str,			# ws_url
	str,			# lob_dir
	#
	int,			# purge_on_date_change
	int,			# save_interval_min
	#
	int,			# snapshots_queue_max
	int,			# records_max
	#
	int, 			# latency_deque_size
	int,			# latency_sample_min
	int, 			# latency_threshold_ms
	float,			# latency_signal_sleep
	#
	int,			# base_backoff
	int,			# max_backoff
	int, 			# reset_cycle_after
	int,			# reset_backoff_level
	#
	Optional[int],	# ws_ping_interval
	Optional[int],	# ws_ping_timeout
	#
	float,			# dashboard_stream_interval
	int,			# max_dashboard_connections
	int,			# max_dashboard_session_sec
	float,			# hardware_monitoring_interval
	float,			# cpu_percent_duration
	float,			# desired_max_sys_mem_load
]:

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

			return [
				s.lower()
				for s in symbols_str.split(",")
				if s.strip()
			]

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to "
				f"extract symbols from {config_path}."
			) from e

	#——————————————————————————————————————————————————————————————

	def extract_others(
		config: dict[str, str]
	) -> tuple[
		str,			# lob_dir
		#
		int,			# purge_on_date_change
		int,			# save_interval_min
		#
		int,			# snapshots_queue_max
		int,			# records_max
		#
		int, 			# latency_deque_size
		int,			# latency_sample_min
		int, 			# latency_threshold_ms
		float,			# latency_signal_sleep
		#
		int,			# base_backoff
		int,			# max_backoff
		int, 			# reset_cycle_after
		int,			# reset_backoff_level
		#
		Optional[int],	# ws_ping_interval
		Optional[int],	# ws_ping_timeout
		#
		float,			# dashboard_stream_interval
		int,			# max_dashboard_connections
		int,			# max_dashboard_session_sec
		float,			# hardware_monitoring_interval
		float,			# cpu_percent_duration
		float,			# desired_max_sys_mem_load
	]:

		try:

			lob_dir = config.get("LOB_DIR")

			purge_on_date_change = int(config.get("PURGE_ON_DATE_CHANGE"))
			save_interval_min	 = int(config.get("SAVE_INTERVAL_MIN"))
			if save_interval_min > 1440:
				raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

			snapshots_queue_max = int(config.get("SNAPSHOTS_QUEUE_MAX"))
			records_max			= int(config.get("RECORDS_MAX"))

			latency_deque_size   = int(config.get("LATENCY_DEQUE_SIZE"))
			latency_sample_min   = int(config.get("LATENCY_SAMPLE_MIN"))
			latency_threshold_ms = int(config.get("LATENCY_THRESHOLD_MS"))
			latency_signal_sleep = float(config.get("LATENCY_SIGNAL_SLEEP"))

			base_backoff		= int(config.get("BASE_BACKOFF"))
			max_backoff			= int(config.get("MAX_BACKOFF"))
			reset_cycle_after   = int(config.get("RESET_CYCLE_AFTER"))
			reset_backoff_level = int(config.get("RESET_BACKOFF_LEVEL"))

			ws_ping_interval = int(config.get("WS_PING_INTERVAL"))
			ws_ping_timeout  = int(config.get("WS_PING_TIMEOUT"))
			if ws_ping_interval == 0: ws_ping_interval = None
			if ws_ping_timeout  == 0: ws_ping_timeout  = None

			dashboard_stream_interval	 = float(config.get("DASHBOARD_STREAM_INTERVAL"))
			max_dashboard_connections	 = int(config.get("MAX_DASHBOARD_CONNECTIONS"))
			max_dashboard_session_sec	 = int(config.get("MAX_DASHBOARD_SESSION_SEC"))
			hardware_monitoring_interval = float(config.get("HARDWARE_MONITORING_INTERVAL"))
			cpu_percent_duration		 = float(config.get("CPU_PERCENT_DURATION"))
			desired_max_sys_mem_load	 = float(config.get("DESIRED_MAX_SYS_MEM_LOAD"))

			return (
				lob_dir,
				#
				purge_on_date_change,
				save_interval_min,
				#
				snapshots_queue_max,
				records_max,
				#
				latency_deque_size,
				latency_sample_min,
				latency_threshold_ms,
				latency_signal_sleep,
				#
				base_backoff,
				max_backoff,
				reset_cycle_after,
				reset_backoff_level,
				#
				ws_ping_interval,
				ws_ping_timeout,
				#
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
		
		symbols = extract_symbols(config)
		(
			lob_dir,
			#
			purge_on_date_change, save_interval_min,
			#
			snapshots_queue_max, records_max,
			#
			latency_deque_size, latency_sample_min,
			latency_threshold_ms, latency_signal_sleep,
			#
			base_backoff, max_backoff,
			reset_cycle_after, reset_backoff_level,
			#
			ws_ping_interval, ws_ping_timeout,
			#
			dashboard_stream_interval,
			max_dashboard_connections,
			max_dashboard_session_sec,
			hardware_monitoring_interval,
			cpu_percent_duration,
			desired_max_sys_mem_load
			#
		) = extract_others(config)

		if not symbols:

			raise RuntimeError(
				f"No SYMBOLS loaded from config."
			)

		ws_url = (
			f"wss://stream.binance.com:9443/stream?streams="
			f"{'/'.join(f'{sym}@depth20@100ms' for sym in symbols)}"
		)

		return (
			symbols,
			ws_url,
			#
			lob_dir,
			#
			purge_on_date_change, save_interval_min,
			#
			snapshots_queue_max, records_max,
			#
			latency_deque_size, latency_sample_min,
			latency_threshold_ms, latency_signal_sleep,
			#
			base_backoff, max_backoff,
			reset_cycle_after, reset_backoff_level,
			#
			ws_ping_interval, ws_ping_timeout,
			#
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
	median_latency_dict:	dict[str, int],
	latest_json_flush:		dict[str, int],
	json_flush_interval:	dict[str, deque[int]],
	put_snapshot_interval:	dict[str, deque[int]],
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	snapshots_queue_max:	int,
	symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
	records_merged_dates:	dict[str, OrderedDict[str]],
	records_znr_minutes:	dict[str, OrderedDict[str]],
	symbols:				list[str],
	logger:					logging.Logger,
	monitoring_deque_len:	int = 100,
) -> tuple[
	asyncio.Event,
	asyncio.Event,
	asyncio.Event,
]:

	try:

		median_latency_dict.clear()
		median_latency_dict.update({
			symbol: None
			for symbol in symbols
		})

		latest_json_flush.clear()
		latest_json_flush.update({
			symbol: get_current_time_ms()
			for symbol in symbols
		})

		json_flush_interval.clear()
		json_flush_interval.update({
			symbol: deque(maxlen=monitoring_deque_len)
			for symbol in symbols
		})

		put_snapshot_interval.clear()
		put_snapshot_interval.update({
			symbol: deque(maxlen=monitoring_deque_len)
			for symbol in symbols
		})

		snapshots_queue_dict.clear()
		snapshots_queue_dict.update({
			symbol: asyncio.Queue(
				maxsize=snapshots_queue_max
			)
			for symbol in symbols
		})

		symbol_to_file_handles.clear()

		records_merged_dates.clear()
		records_merged_dates.update({
			symbol: OrderedDict()
			for symbol in symbols
		})

		records_znr_minutes.clear()
		records_znr_minutes.update({
			symbol: OrderedDict()
			for symbol in symbols
		})

		logger.info(
			f"[{my_name()}] "
			f"Runtime state initialized."
		)

		event_1st_snapshot  = asyncio.Event()
		event_latency_valid = asyncio.Event()
		event_stream_enable = asyncio.Event()

		return (
			event_1st_snapshot,
			event_latency_valid,
			event_stream_enable,
		)

	except Exception as e:

		logger.error(
			f"[{my_name()}] Failed to "
			f"initialize runtime state: {e}",
			exc_info=True
		)
		raise SystemExit from e

#———————————————————————————————————————————————————————————————————————————————