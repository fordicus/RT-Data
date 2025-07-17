from concurrent.futures import ProcessPoolExecutor
import inspect, os, asyncio, threading, json, logging
from io import TextIOWrapper
from typing import Dict, Optional
import logging

# ——————————————————————————————————————————————————————————————————————

def get_current_time_ms():		return	# TODO: define in global

# ——————————————————————————————————————————————————————————————————————

async def symbol_dump_snapshot(
	symbol:					str,
	save_interval_min:		int,
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	event_stream_enable:	asyncio.Event,
	lob_dir:				str,
	symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
	json_flush_interval:	Dict[str, int],
	latest_json_flush:		Dict[str, int],
	purge_on_date_change:	int,
	merge_executor:			ProcessPoolExecutor,
	merged_days:			dict[str, set[str]],
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
	) -> Optional[Dict]:

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

	def get_date_from_suffix(suffix: str) -> str:

		# '2025-06-27_13-15' -> '2025-06-27'

		try: return suffix.split("_")[0]

		except Exception as e:

			logger.error(
				f"[{my_name()}] Failed to extract date "
				f"from suffix '{suffix}': {e}",
				exc_info=True
			)
			return "invalid_date"

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
		snapshot: Dict,
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

	def zip_and_remove(src_path: str):

		try:

			if os.path.exists(src_path):

				zip_path = src_path.replace(".jsonl", ".zip")

				with zipfile.ZipFile(
					zip_path, "w", zipfile.ZIP_DEFLATED
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

	def safe_zip_n_remove_jsonl(
		lob_dir:	  str,
		symbol_upper: str,
		last_suffix:  str,
		logger:		  logging.Logger
	):

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

	def flush_snapshot(
		json_writer: TextIOWrapper,
		snapshot: Dict,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
		json_flush_interval: Dict[str, int],
		latest_json_flush: Dict[str, int],
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

	def symbol_trigger_merge(
		merge_executor: ProcessPoolExecutor,
		purge_on_date_change: int,
		lob_dir:   str,
		symbol:	   str,
		last_date: str
	):

		merge_executor.submit(
			symbol_consolidate_a_day,	# TODO: defined in global
			symbol, last_date,			# pickle
			lob_dir,
			purge_on_date_change == 1
		)

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
		# STEP 1
		# 	safe_zip_n_remove_jsonl(last_jsonl_path)
		#	json_writer = open(file_path, "a", encoding="utf-8")
		# ────────────────────────────────────────────────────────────────────
		# `last_suffix` will be `None` at the beginning.
		# ────────────────────────────────────────────────────────────────────

		last_suffix, json_writer = symbol_to_file_handles.get(
			symbol, (None, None))

		if last_suffix != suffix:

			if json_writer:

				# ────────────────────────────────────────────────────────────

				if not safe_close_jsonl(json_writer):

					logger.warning(
						f"[{my_name()}][{symbol.upper()}] "
						f"JSON writer may not "
						f"have been closed."
					)

				del json_writer

				# ────────────────────────────────────────────────────────────

				try:

					safe_zip_n_remove_jsonl(
						lob_dir, symbol_upper,
						last_suffix, logger
					)

				except Exception as e:

					logger.error(
						f"[{my_name()}][{symbol_upper}] "
						f"safe_zip_n_remove_jsonl() failed "
						f"for last_suffix={last_suffix}: {e}",
						exc_info=True
					)
					del e

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
					(last_date not in merged_days[symbol])
				):

					merged_days[symbol].add(last_date)		# TODO: deque
					
					symbol_trigger_merge(
						merge_executor,
						purge_on_date_change,
						lob_dir, symbol, last_date
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
				f"Failed to flush snapshot: {e}",
				exc_info=True
			)

		del snapshot, file_path
