# ───────────────────────────────────────────────────────────────────────────────

from stream_binance_globals import (
	my_name,							# For exceptions with 0 Lebesgue measure
	get_current_time_ms,
	ms_to_datetime,
)

from io import TextIOWrapper
from collections import OrderedDict
from typing import Optional
from concurrent.futures import ProcessPoolExecutor

import os, io, asyncio, json, logging

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

	#——————————————————————————————————————————————————————————————

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

	#——————————————————————————————————————————————————————————————

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

		# discard the oldest at the front of the container
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
						symbol_consolidate_a_day,
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