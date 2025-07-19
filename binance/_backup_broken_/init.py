import logging, globals
from collections import deque
from util import my_name
# from globals import(
# 	SYMBOLS,				# list[str],
# 	SNAPSHOTS_QUEUE_DICT,	# dict[str, asyncio.Queue],
# 	SYMBOL_TO_FILE_HANDLES,	# dict[str, tuple[str, TextIOWrapper]],
# 	RECORDS_MERGED_DATES,	# dict[str, OrderedDict[str]],
# 	RECORDS_ZNR_MINUTES,	# dict[str, OrderedDict[str]],
# 	LATENCY_DICT,			# dict[str, deque[int]],
# 	MEDIAN_LATENCY_DICT,	# dict[str, int],
# 	DEPTH_UPDATE_ID_DICT,	# dict[str, int],
# 	LATEST_JSON_FLUSH,		# dict[str, int],
# 	JSON_FLUSH_INTERVAL,	# dict[str, int],
# )

#———————————————————————————————————————————————————————————————————

def init_runtime_state(
	logger: logging.Logger,
	snapshots_queue_max: int = 100,
	latency_deque_size:  int =  10,
):

	try:

		#──────────────────────────────────────────────────────────
		
		globals.SNAPSHOTS_QUEUE_DICT.clear()
		globals.SNAPSHOTS_QUEUE_DICT.update({
			symbol: asyncio.Queue(maxsize=snapshots_queue_max)
			for symbol in globals.SYMBOLS
		})

		globals.SYMBOL_TO_FILE_HANDLES.clear()

		globals.RECORDS_MERGED_DATES.clear()
		globals.RECORDS_MERGED_DATES.update({
			symbol: OrderedDict()
			for symbol in globals.SYMBOLS
		})

		globals.RECORDS_ZNR_MINUTES.clear()
		globals.RECORDS_ZNR_MINUTES.update({
			symbol: OrderedDict()
			for symbol in globals.SYMBOLS
		})

		#──────────────────────────────────────────────────────────

		print(f"SYMBOLS: {globals.SYMBOLS}")
		print(f"LATENCY_DICT: {globals.LATENCY_DICT}")

		globals.LATENCY_DICT.clear()
		globals.LATENCY_DICT.update({
			symbol: deque(maxlen=latency_deque_size)
			for symbol in globals.SYMBOLS
		})

		print(f"SYMBOLS: {globals.SYMBOLS}")
		print(f"LATENCY_DICT: {globals.LATENCY_DICT}"); exit()

		globals.MEDIAN_LATENCY_DICT.clear()
		globals.MEDIAN_LATENCY_DICT.update({
			symbol: 0
			for symbol in globals.SYMBOLS
		})

		globals.DEPTH_UPDATE_ID_DICT.clear()
		globals.DEPTH_UPDATE_ID_DICT.update({
			symbol: 0
			for symbol in globals.SYMBOLS
		})

		globals.LATEST_JSON_FLUSH.clear()
		globals.LATEST_JSON_FLUSH.update({
			symbol: get_current_time_ms()
			for symbol in globals.SYMBOLS
		})

		globals.JSON_FLUSH_INTERVAL.clear()
		globals.JSON_FLUSH_INTERVAL.update({
			symbol: 0
			for symbol in globals.SYMBOLS
		})

		logger.info(
			f"[{my_name()}] Runtime state initialized."
		)

		#──────────────────────────────────────────────────────────

	except Exception as e:

		logger.critical(
			f"[{my_name()}] "
			f"Failed to initialize runtime state: {e}",
			exc_info=True
		)
		raise SystemExit

#——————————————————————————————————————————————————————————————————