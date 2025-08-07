# core.py

#———————————————————————————————————————————————————————————————————————————————

from util import (
	my_name,
	NanoTimer,
	ms_to_datetime,
	compute_bias_ms,
	format_ws_url,
	get_current_time_ms,
	get_global_log_queue,
	get_subprocess_logger,
	ensure_logging_on_exception,
	force_print_exception,
)

from hotswap import (
	HotSwapManager,
	schedule_backup_creation,
)

import sys, os, io, asyncio, orjson
import shutil, zipfile, logging
import websockets, time, random
import numpy as np

from io import TextIOWrapper
from collections import OrderedDict, deque
from typing import Optional
from concurrent.futures import ProcessPoolExecutor

#———————————————————————————————————————————————————————————————————————————————
#	 '2025-06-27_13-15'
# -> '2025-06-27'
#———————————————————————————————————————————————————————————————————————————————

def get_date_from_suffix(suffix: str) -> str:

	try: return suffix.split("_")[0]

	except Exception as e:

		raise RuntimeError(
			f"[{my_name()}] Failed to extract date "
			f"from suffix '{suffix}': {e}"
		) from e

#———————————————————————————————————————————————————————————————————————————————

def proc_zip_n_remove_jsonl(
	lob_dir:	  str,
	symbol_upper: str,
	last_suffix:  str,
	max_retries: int   = 100,
	retry_delay: float = 0.1,
	exp_backoff: float = 1.2,
):

	#———————————————————————————————————————————————————————————————————————————

	def zip_and_remove(src_path: str):

		try:

			zip_path = src_path.replace(".jsonl", ".zip")

			current_retry_delay = retry_delay

			# 🔧 Retry logic for zip creation with integrity verification

			for attempt in range(max_retries):

				try:

					with zipfile.ZipFile(	# Create zip file
						zip_path, "w",
						zipfile.ZIP_DEFLATED
					) as zf:

						zf.write(src_path,
							arcname=os.path.basename(src_path)
						)

					# Verify zip integrity immediately after creation

					with zipfile.ZipFile(zip_path, "r") as test_zf:

						test_zf.testzip()

					break  # Success, exit retry loop

				except (zipfile.BadZipFile, OSError, IOError) as e:

					if attempt == max_retries - 1:

						get_subprocess_logger().error(
							f"[{my_name()}] "
							f"Zip creation failed after "
							f"{max_retries} attempts: "
							f"{zip_path} → {e}",
							exc_info=True
						)
						raise

					get_subprocess_logger().warning(
						f"[{my_name()}] "
						f"Zip creation not ready "
						f"(attempt {attempt + 1}/{max_retries}): "
						f"{zip_path}, retrying in {current_retry_delay}s..."
					)

					# Clean up partial zip file if it exists

					try:

						if os.path.exists(zip_path):

							os.remove(zip_path)

					except Exception:

						pass

					time.sleep(current_retry_delay)
					current_retry_delay *= exp_backoff

			# Remove source .jsonl file only after successful zip creation

			os.remove(src_path)

		except FileNotFoundError:

			get_subprocess_logger().warning(
				f"[{my_name()}] Source file not found "
				f"somehow: {src_path}"
			)

		except Exception as e:
			
			get_subprocess_logger().error(
				f"[{my_name()}] Failed to "
				f"zip and remove {src_path}: {e}",
				exc_info=True
			)
			raise

	#———————————————————————————————————————————————————————————————————————————

	try:

		# get_subprocess_logger().warning(
		# 	f"\tproc_zip_n_remove_jsonl() invoked"
		# )

		last_jsonl_path = os.path.join(
			os.path.join(
				lob_dir, "temporary",
				f"{symbol_upper}_orderbook_"
				f"{get_date_from_suffix(last_suffix)}",
			),
			f"{symbol_upper}_orderbook_{last_suffix}.jsonl"
		)

		zip_and_remove(last_jsonl_path)

	except Exception as e:

		get_subprocess_logger().error(
			f"[{my_name()}][{symbol_upper}] "
			f"Failed to process {last_suffix}: {e}",
			exc_info=True
		)
		raise

#———————————————————————————————————————————————————————————————————————————————

def proc_symbol_consolidate_a_day(
	symbol:		 str,
	day_str: 	 str,
	base_dir:	 str,
	max_retries: int   = 100,
	retry_delay: float = 0.1,
	exp_backoff: float = 1.2,
	purge:		 bool  = True,
):

	with NanoTimer() as timer:

		#———————————————————————————————————————————————————————————————————————

		logger = get_subprocess_logger()

		# Construct working directories and target paths

		tmp_dir = os.path.join(base_dir, "temporary",
			f"{symbol.upper()}_orderbook_{day_str}"
		)

		merged_path = os.path.join(base_dir,
			f"{symbol.upper()}_orderbook_{day_str}.jsonl"
		)

		if not os.path.isdir(tmp_dir):

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Temp dir missing on {day_str}: {tmp_dir}"
			)

			return

		#———————————————————————————————————————————————————————————————————————
		# List all zipped minute-level files (may be empty)
		#———————————————————————————————————————————————————————————————————————

		try:

			zip_files = [
				f for f in os.listdir(tmp_dir)
				if f.endswith(".zip")
			]

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to list zips in {tmp_dir}: {e}",
				exc_info=True
			)

			return

		if not zip_files:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"No zip files to merge on {day_str}."
			)

			return

		#———————————————————————————————————————————————————————————————————————
		# File handle management with proper scope handling
		#———————————————————————————————————————————————————————————————————————

		fout = None

		try:

			# Open output file for merged .jsonl content

			fout = open(merged_path, "w", encoding="utf-8")

			# Initialize current_retry_delay as local variable

			current_retry_delay = retry_delay

			# Process each zip file in chronological order

			for zip_file in sorted(zip_files):

				zip_path = os.path.join(tmp_dir, zip_file)

				# Wait for zip file to be fully ready
				
				for attempt in range(max_retries):

					try:

						# Test if file is a valid zip

						with zipfile.ZipFile(zip_path, "r") as test_zf:

							test_zf.testzip()  # Verify zip integrity

						break  # Success, exit retry loop
						
					except (zipfile.BadZipFile, FileNotFoundError) as e:

						if attempt == max_retries - 1:

							logger.error(
								f"[{my_name()}][{symbol.upper()}] "
								f"Zip file still invalid after "
								f"{max_retries} attempts: "
								f"{zip_path} → {e}"
							)
							return
						
						logger.warning(
							f"[{my_name()}][{symbol.upper()}] "
							f"Zip file not ready "
							f"(attempt {attempt + 1}/{max_retries}): "
							f"{zip_path}, retrying in {current_retry_delay}s..."
						)

						time.sleep(current_retry_delay)
						current_retry_delay *= exp_backoff
						# Exponential backoff

				try:
					with zipfile.ZipFile(zip_path, "r") as zf:
						for member in zf.namelist():
							with zf.open(member) as f:
								for raw in f:
									fout.write(raw.decode("utf-8"))

				except Exception as e:

					logger.error(
						f"[{my_name()}][{symbol.upper()}]\n"
						f"Failed to extract {zip_path}: {e}",
						exc_info=True
					)

					return

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to open or write to merged file "
				f"{merged_path}: {e}",
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
						f"[{my_name()}][{symbol.upper()}] "
						f"Failed to close output file: "
						f"{close_error}",
						exc_info=True
					)

		#———————————————————————————————————————————————————————————————————————
		# Recompress the consolidated .jsonl
		# into a final single-archive zip
		#———————————————————————————————————————————————————————————————————————

		try:

			final_zip = merged_path.replace(".jsonl", ".zip")

			with zipfile.ZipFile(
				final_zip, "w",
				zipfile.ZIP_DEFLATED
			) as zf:

				zf.write(
					merged_path,
					arcname=os.path.basename(merged_path)
				)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to compress merged "
				f"file on {day_str}: {e}",
				exc_info=True
			)

			# Do not remove .jsonl if compression failed

			return

		# Remove intermediate plain-text .jsonl file
		# after compression

		try:

			if os.path.exists(merged_path):

				os.remove(merged_path)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to remove merged .jsonl "
				f"on {day_str}: {e}",
				exc_info=True
			)

		# Optionally delete the original temp folder
		# containing per-minute zips

		if purge:

			try:

				shutil.rmtree(tmp_dir)

			except Exception as e:

				logger.error(
					f"[{my_name()}][{symbol.upper()}] "
					f"Failed to remove temp dir "
					f"{tmp_dir}: {e}",
					exc_info=True
				)

		logger.info(
			f"[{my_name()}][{symbol.upper()}] "
			f"Successfully merged {len(zip_files)} files "
			f"for {day_str} (took {timer.tock():.5f} sec)."
		)

#———————————————————————————————————————————————————————————————————————————————

@ensure_logging_on_exception
async def symbol_dump_snapshot(
	symbol:					str,
	save_interval_min:		int,
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	# it seems unnecessary in `symbol_dump_snapshot`
	# event_stream_enable:	asyncio.Event,
	lob_dir:				str,
	symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
	json_flush_interval:	dict[str, deque[int]],
	latest_json_flush:		dict[str, int],
	purge_on_date_change:	int,
	merge_executor:			ProcessPoolExecutor,
	records_merged_dates:	dict[str, OrderedDict[str, None]],
	znr_executor:			ProcessPoolExecutor,
	records_znr_minutes:	dict[str, OrderedDict[str, None]],
	records_max:			int,
	logger:					logging.Logger,
	shutdown_event:			Optional[asyncio.Event] = None,
	file_sync_delay_sec:	float = 0.0005,
):

	#———————————————————————————————————————————————————————————————————————————————

	def is_shutting_down():

		return (
			shutdown_event
			and shutdown_event.is_set()
		)

	#———————————————————————————————————————————————————————————————————————————————

	def safe_close_file_muted(
		f: TextIOWrapper
	):

		if f is not None and hasattr(f, 'close'):
			try:   f.close()
			except Exception: pass

	#———————————————————————————————————————————————————————————————————————————————

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

	#———————————————————————————————————————————————————————————————————————————————
	
	def refresh_file_handle(
		file_path: str,
		suffix: str,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
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

	#———————————————————————————————————————————————————————————————————————————————

	def pop_and_close_handle(
		handles: dict[str, tuple[str, TextIOWrapper]],
		symbol: str
	):

		try:

			tup = handles.pop(symbol, None)	# not only `pop` from dict
			if tup is not None:
				safe_close_file_muted(tup[1])		# but also `close`

		except Exception: pass

	#———————————————————————————————————————————————————————————————————————————————

	async def fetch_snapshot(
		queue:  asyncio.Queue,
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

	#———————————————————————————————————————————————————————————————————————————————

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

	#———————————————————————————————————————————————————————————————————————————————

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
	
	#———————————————————————————————————————————————————————————————————————————————

	async def gen_file_path(
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
			await asyncio.to_thread(
				os.makedirs,
				temp_dir,
				exist_ok=True,
			)
			return os.path.join(temp_dir, file_name)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to build file path: {e}",
				exc_info=True
			)
			return None

	#———————————————————————————————————————————————————————————————————————————————

	def flush_snapshot(
		json_writer: TextIOWrapper,
		snapshot: dict,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
		json_flush_interval:	dict[str, deque[int]],
		latest_json_flush:		dict[str, int],
		file_path: str,
	) -> bool:
		
		try:

			if json_writer.closed:
				
				if is_shutting_down():

					return True

				else:

					logger.warning(
						f"[{my_name()}][{symbol.upper()}] "
						f"attempted to write to closed file: {file_path}"
					)

					return False

			json_writer.write(
				orjson.dumps(snapshot).decode() + "\n"
			)
			json_writer.flush()

			cur_time_ms = get_current_time_ms()

			json_flush_interval[symbol].append(
				cur_time_ms - latest_json_flush[symbol]
			)
			
			latest_json_flush[symbol] = cur_time_ms

			return True

		except ValueError as e:

			if "closed file" in str(e): return False

			else: raise  # Propagate any other ValueError

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"write failed: {file_path} → {e}",
				exc_info=True
			)

			try:

				# Invalidate `json_writer` for next iteration

				pop_and_close_handle(
					symbol_to_file_handles, symbol
				)

			except Exception: pass

			return False
		
	#———————————————————————————————————————————————————————————————————————————————

	def memorize_treated(
		records: dict[str, OrderedDict[str, None]],
		records_max: int,
		symbol: str,
		to_rec: str
	):

		try:

			# discard the oldest at the front of the container
			if len(records[symbol]) >= records_max:
				records[symbol].popitem(last=False)
			records[symbol][to_rec] = None

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to memorize treated record "
				f"for symbol='{symbol}', to_rec='{to_rec}': {e}"
			) from e

	#———————————————————————————————————————————————————————————————————————————————

	queue = snapshots_queue_dict[symbol]
	symbol_upper = symbol.upper()
	
	last_snapshot_time_ms = None

	try:

		while not is_shutting_down():	# infinite standalone loop

			#———————————————————————————————————————————————————————————————————————————

			snapshot = await fetch_snapshot(queue, symbol)
			
			if snapshot is None:
				logger.warning(
					f"[{my_name()}][{symbol_upper}] "
					f"snapshot is None, skipping iteration."
				)
				continue

			# it seems unnecessary in `symbol_dump_snapshot`
			# if not event_stream_enable.is_set():
			# 	continue
			
			suffix, date_str = get_suffix_n_date(
				save_interval_min,
				snapshot, symbol
			)

			if ((suffix is None) or (date_str is None)):
				logger.warning(
					f"[{my_name()}][{symbol_upper}] "
					f"suffix or date string is None, "
					f"skipping iteration."
				)
				continue

			file_path = await gen_file_path(
				symbol_upper, suffix,
				lob_dir, date_str
			)
			
			if file_path is None:
				logger.warning(
					f"[{my_name()}][{symbol_upper}] "
					f"file path is None, "
					f"skipping iteration."
				)
				continue

			#─────────────────────────────────────────────────────────────────────
			# STEP 1: Roll-over by Minute
			#─────────────────────────────────────────────────────────────────────
			# `last_suffix` will be `None` at the beginning.
			#─────────────────────────────────────────────────────────────────────

			last_suffix, json_writer = symbol_to_file_handles.get(
				symbol, (None, None))

			if last_suffix != suffix:

				# logger.warning(
				# 	f"\n"
				# 	f"\tsuffix:	{suffix}\n"
				# 	f"\tlast_s: {last_suffix}\n"
				# )

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

					# logger.warning(
					# 	f"\trecords_znr_minutes[symbol]: "
					# 	f"{records_znr_minutes[symbol]}"
					# )

					await asyncio.sleep(file_sync_delay_sec)

					if last_suffix not in records_znr_minutes[symbol]:

						memorize_treated(
							records_znr_minutes,
							records_max,
							symbol, last_suffix
						)

						# logger.warning(f"\tznr_executor.submit()")

						znr_executor.submit(	# pickle
							proc_zip_n_remove_jsonl,
							lob_dir, symbol_upper, 
							last_suffix
						)

				# ────────────────────────────────────────────────────────────────

				try: 
					
					json_writer = refresh_file_handle(
						file_path, suffix, symbol, 
						symbol_to_file_handles,
					)
					if json_writer is None: continue 

				except Exception as e:

					logger.error(
						f"[{my_name()}][{symbol_upper}] "
						f"Failed to refresh file handles → {e}",
						exc_info=True
					)
					continue

			#─────────────────────────────────────────────────────────────────────
			# STEP 2: Check for day rollover and trigger merge
			# At this point, ALL previous files are guaranteed to be .zip
			#─────────────────────────────────────────────────────────────────────

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
							proc_symbol_consolidate_a_day,
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

			#─────────────────────────────────────────────────────────────────────
			# STEP 3: Write snapshot to file and update flush intervals
			#─────────────────────────────────────────────────────────────────────

			if last_snapshot_time_ms is not None:

				if (
					snapshot['recv_ms']
					< last_snapshot_time_ms
				):

					logger.critical(
						f"[{my_name()}] "
						f"snapshot timestamp order reversed: "
						f"{snapshot['recv_ms']} < {last_snapshot_time_ms}"
					)

			last_snapshot_time_ms = snapshot['recv_ms']

			#─────────────────────────────────────────────────────────────────────

			if not flush_snapshot(
				json_writer,
				snapshot,
				symbol,
				symbol_to_file_handles,
				json_flush_interval,
				latest_json_flush,
				file_path,
			):

				logger.error(
					f"[{my_name()}][{symbol_upper}] "
					f"failed to flush snapshot.",
					exc_info=True
				)

			# await asyncio.sleep(1)		# when simulating some delays

			del snapshot, file_path

	except asyncio.CancelledError:

		raise # logging unnecessary

	except Exception as e:

		logger.error(
			f"[{my_name()}][{symbol_upper}] unexpected error: {e}"
		)

	finally:

		logger.info(f"[{my_name()}][{symbol_upper}] task ends")

#———————————————————————————————————————————————————————————————————————————————
# Wrapper to ensure logging of exceptions during asynchronous operations.
#———————————————————————————————————————————————————————————————————————————————

@ensure_logging_on_exception
async def wrapped_put_snapshot(*args, **kwargs):
	try: return await put_snapshot(*args, **kwargs)
	except asyncio.CancelledError: pass
	except Exception as e: raise

#———————————————————————————————————————————————————————————————————————————————

@ensure_logging_on_exception
async def put_snapshot(					# @depth20@100ms
	#———————————————————————————————————————————————————————————————————————————
	# Liveness Monitoring
	#———————————————————————————————————————————————————————————————————————————
	websocket_recv_interval:			deque[float],
	websocket_recv_intv_stat:			dict[str, float],
	put_snapshot_interval:				dict[str, deque[int]],
	#———————————————————————————————————————————————————————————————————————————
	# Datafication
	#———————————————————————————————————————————————————————————————————————————
	snapshots_queue_dict:				dict[str, asyncio.Queue],
	#———————————————————————————————————————————————————————————————————————————
	# Latency Control
	#———————————————————————————————————————————————————————————————————————————
	event_stream_enable:				asyncio.Event,
	mean_latency_dict:					dict[str, int],
	event_1st_snapshot:					asyncio.Event,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Recovery
	#———————————————————————————————————————————————————————————————————————————
	max_backoff:						int, 
	base_backoff:						int,
	reset_cycle_after:					int,
	reset_backoff_level:				int,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Peer
	#———————————————————————————————————————————————————————————————————————————
	ws_url:								str,
	wildcard_stream_binance_com_port:	str,
	ports_stream_binance_com:			list[str],
	ws_ping_interval:					int,
	ws_ping_timeout:					int,
	#———————————————————————————————————————————————————————————————————————————
	# Combined Streams & Logging
	#———————————————————————————————————————————————————————————————————————————
	symbols:							list[str],
	logger:								logging.Logger,
	#———————————————————————————————————————————————————————————————————————————
	# Howswap Websockets
	#———————————————————————————————————————————————————————————————————————————
	port_cycling_period_hrs:			float,
	back_up_ready_ahead_sec:			float,
	hotswap_manager:					HotSwapManager,
	shutdown_event:						Optional[asyncio.Event] = None,
	handoff_event:						Optional[asyncio.Event] = None,
	is_backup:							bool = False,
	hotswap_tolerance_sec:				float = 60.0,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Liveness Control
	#———————————————————————————————————————————————————————————————————————————
	base_interval_ms:					int	  = 100,
	ws_timeout_multiplier:				float =	  8.0,
	ws_timeout_default_sec:				float =	  2.0,
	ws_timeout_min_sec:					float =	  1.0,	
	#———————————————————————————————————————————————————————————————————————————
):

	"""—————————————————————————————————————————————————————————————————————————
	HINT:
		asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
	—————————————————————————————————————————————————————————————————————————"""

	def update_ws_recv_timeout(		# to detect websockets with no data
		data:		deque[float],
		stat:		dict[str, float],
		multiplier: float,
		default:	float,
		minimum:	float,
	) -> float:		# ws_timeout_sec (adaptive based on statistics)

		if len(data) >= max(data.maxlen, 300):
			
			stat['p90'] = np.percentile(list(data), 90)
			return max(stat['p90'] * multiplier, minimum)

		else:

			return max(default, minimum)

	#———————————————————————————————————————————————————————————————————————————

	async def calculate_backoff_and_sleep(		# back-off when ws fails
		retry_count: int,
		last_success_time: Optional[float] = None,
		reset_retry_count_after_sec: float = 3600.0,
	) -> tuple[int, float]:
		
		current_time = time.time()
		
		if retry_count > reset_cycle_after:

			retry_count = reset_backoff_level

		elif (
			last_success_time and 
			(
				current_time - last_success_time
			) > reset_retry_count_after_sec
		):

			logger.info(
				f"[{my_name()}] "
				f"resetting retry_count after "
				f"{reset_retry_count_after_sec} sec; "
				f"previous retry_count={retry_count}."
			)

			retry_count = 0

		backoff = min(
			max_backoff,
			base_backoff ** retry_count
		) + random.uniform(0, 1)

		logger.warning(
			f"[{my_name()}] "
			f"Retrying in {backoff:.1f} seconds..."
		)
		
		await asyncio.sleep(backoff)
		
		return retry_count, last_success_time

	#———————————————————————————————————————————————————————————————————————————

	def cycle_port_number(						# utilize various ws ports
		ports_list: list[str],
		hotswap_manager: HotSwapManager,
	) -> tuple[str, int]:
		
		new_index = (
			hotswap_manager.get_next_port_index(len(ports_list))
		)

		return ports_list[new_index], new_index

	#———————————————————————————————————————————————————————————————————————————
	# Howswap State
	#———————————————————————————————————————————————————————————————————————————

	refresh_period_sec = (				# unit conversion
		port_cycling_period_hrs
		* 3600.0
	)

	is_active_conn = not is_backup		# backup starts inactive
	backup_start_time = (				# backup starts earlier
		refresh_period_sec 
		- back_up_ready_ahead_sec
	)

	hotswap_prepared = False

	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Liveness Control
	#———————————————————————————————————————————————————————————————————————————

	ws_retry_cnt = 0
	ws_timeout_sec	  = ws_timeout_default_sec
	last_success_time = time.time()
	last_recv_time_ns = None
	
	measured_interval_ms: dict[str, int] = {}
	measured_interval_ms.clear()
	measured_interval_ms.update({
		symbol: None
		for symbol in symbols
	})
	
	prev_snapshot_time_ms: dict[str, int] = {}
	prev_snapshot_time_ms.clear()
	prev_snapshot_time_ms.update({
		symbol: None
		for symbol in symbols
	})

	#———————————————————————————————————————————————————————————————————————————
	# [DEBUG] We can simulate a specific time via `bias_to_add` if necessary.
	#———————————————————————————————————————————————————————————————————————————

	# from datetime import datetime
	# target_dt = datetime(
	# 	2025,  7, 24, 
	# 	  23, 59, 50
	# )
	# bias_to_add = compute_bias_ms(get_current_time_ms(), target_dt,)

	#———————————————————————————————————————————————————————————————————————————

	while not hotswap_manager.is_shutting_down():	# infinite standalone loop

		cur_symbol = "UNKNOWN"

		try:

			#———————————————————————————————————————————————————————————————————
			# Determine Port Number → WS Peer's URL
			#———————————————————————————————————————————————————————————————————

			target_port, cur_port_index = cycle_port_number(
				ports_stream_binance_com,
				hotswap_manager,
			)

			ws_url_complete = ws_url.replace(
				wildcard_stream_binance_com_port,
				target_port,
			)

			#———————————————————————————————————————————————————————————————————
			# Within WebSocket
			#———————————————————————————————————————————————————————————————————

			async with websockets.connect(
				ws_url_complete,
				ping_interval = ws_ping_interval,
				ping_timeout  = ws_ping_timeout
			) as ws:

				#———————————————————————————————————————————————————————————————

				ws_retry_cnt = 0
				last_success_time = time.time()
				ws_start_time	  = time.time()

				ws_url_to_prt = format_ws_url(
					ws_url_complete,
					symbols,
					ports_stream_binance_com,
				)

				logger.info(
					f"[{my_name()}]🟢\n  "
					f"{ws_url_to_prt} "
					f"(is_backup: {int(is_backup)})"
				)

				#———————————————————————————————————————————————————————————————
				# backup → main → prepare (next_schedule_task)
				#———————————————————————————————————————————————————————————————

				if (
					is_backup
					and handoff_event
				):

					logger.info(f"[{my_name()}]🕒 backup standby")

					try:

						#———————————————————————————————————————————————————————
						# awaiting handoff event trigger: backup → main
						#———————————————————————————————————————————————————————

						await asyncio.wait_for(
							handoff_event.wait(), 
							timeout = back_up_ready_ahead_sec * 2.0,
						)
						is_active_conn = True
						logger.info(
							f"[{my_name()}]🔥 backup → main"
						)

						#———————————————————————————————————————————————————————
						# prepare (next_schedule_task)
						#———————————————————————————————————————————————————————

						next_schedule_task = asyncio.create_task(
							schedule_backup_creation(
								#———————————————————————————————————————————
								hotswap_manager,
								backup_start_time,
								#———————————————————————————————————————————
								lambda event, backup: wrapped_put_snapshot(
									#———————————————————————————————————————
									websocket_recv_interval,
									websocket_recv_intv_stat,
									put_snapshot_interval,
									#———————————————————————————————————————
									snapshots_queue_dict,
									#———————————————————————————————————————
									event_stream_enable,
									mean_latency_dict,
									event_1st_snapshot,
									#———————————————————————————————————————
									max_backoff,
									base_backoff,
									reset_cycle_after,
									reset_backoff_level,
									#———————————————————————————————————————
									ws_url,
									wildcard_stream_binance_com_port,
									ports_stream_binance_com,
									ws_ping_interval,
									ws_ping_timeout,
									#———————————————————————————————————————
									symbols,
									logger,
									#———————————————————————————————————————
									port_cycling_period_hrs,
									back_up_ready_ahead_sec,
									hotswap_manager,
									shutdown_event,
									event,
									backup,
									#———————————————————————————————————————
								),
								#———————————————————————————————————————————
								logger,
								back_up_ready_ahead_sec,
								ws_start_time,
								#———————————————————————————————————————————
							)
						)

						hotswap_manager.hot_swap_tasks.append(
							next_schedule_task
						)
						
						logger.info(
							f"[{my_name()}]📅 next backup scheduled"
						)

					#———————————————————————————————————————————————————————————
					# unutilized backup returns
					#———————————————————————————————————————————————————————————

					except asyncio.TimeoutError:

						logger.warning(
							f"[{my_name()}] backup handoff timeout, "
							f"terminating backup"
						)
						return

					#———————————————————————————————————————————————————————————
					# backup returns whenever there's an exception
					#———————————————————————————————————————————————————————————

					except Exception as e:

						logger.error(
							f"[{my_name()}] backup connection error: {e}"
						)
						return

				#———————————————————————————————————————————————————————————————
				# main: prepare (schedule_task)
				#———————————————————————————————————————————————————————————————

				elif (
					not is_backup
					and not hotswap_prepared
				):

					hotswap_prepared = True
					
					# schedule_backup_creation 태스크 생성 및 등록

					schedule_task = asyncio.create_task(
						schedule_backup_creation(
							#———————————————————————————————————————————
							hotswap_manager,
							backup_start_time,
							#———————————————————————————————————————————
							lambda event, backup: wrapped_put_snapshot(
								#———————————————————————————————————————
								websocket_recv_interval,
								websocket_recv_intv_stat,
								put_snapshot_interval,
								#———————————————————————————————————————
								snapshots_queue_dict,
								#———————————————————————————————————————
								event_stream_enable,
								mean_latency_dict,
								event_1st_snapshot,
								#———————————————————————————————————————
								max_backoff,
								base_backoff,
								reset_cycle_after,
								reset_backoff_level,
								#———————————————————————————————————————
								ws_url,
								wildcard_stream_binance_com_port,
								ports_stream_binance_com,
								ws_ping_interval,
								ws_ping_timeout,
								#———————————————————————————————————————
								symbols,
								logger,
								#———————————————————————————————————————
								port_cycling_period_hrs,
								back_up_ready_ahead_sec,
								hotswap_manager,
								shutdown_event,
								event,
								backup,
								#———————————————————————————————————————
							),
							#———————————————————————————————————————————
							logger,
							back_up_ready_ahead_sec,
							ws_start_time,
							#———————————————————————————————————————————
						)
					)

					hotswap_manager.hot_swap_tasks.append(schedule_task)

					logger.info(
						f"[{my_name()}]📅 backup scheduled"
					)

				#———————————————————————————————————————————————————————————————
				# loop inside ws
				#———————————————————————————————————————————————————————————————

				while not hotswap_manager.is_shutting_down():

					#———————————————————————————————————————————————————————————
					# main: commence hotswap
					#———————————————————————————————————————————————————————————
					
					if (
						is_active_conn
						and not hotswap_manager.is_shutting_down()
						and (time.time() - ws_start_time) >= refresh_period_sec
					):

						#———————————————————————————————————————————————————————
						
						if hotswap_manager.is_ready_for_handoff():

							try:

								logger.info(
									f"[{my_name()}]🔄 hotswap starts"
								)

								with NanoTimer() as timer:

									await hotswap_manager.commence_hotswap(
										logger,
									)

									logger.info(
										f"[{my_name()}]✅ hotswap done"
										f" in {timer.tock() * 1000.:.3f} ms"
									)

								if (
									hotswap_manager.handoff_completed
									and ws_retry_cnt > 0
								):

									ws_retry_cnt = 0
									last_success_time = time.time()
									hotswap_manager.handoff_completed = False

								return		# main returns

							except Exception as e:

								logger.critical(
									f"[{my_name()}] hotswap failed: "
									f"{e}; task terminates"
								)
								hotswap_prepared = False
								return

						#———————————————————————————————————————————————————————

						else:

							logger.warning(
								f"[{my_name()}] backup not ready; "
								f"continuing with current conn."
							)
							hotswap_prepared = False

					#———————————————————————————————————————————————————————————
					# Messages within WebSocket
					#———————————————————————————————————————————————————————————
					
					try:

						#———————————————————————————————————————————————————————
						# Receive a Message or Shutting Down
						#———————————————————————————————————————————————————————
						
						done, pending = await asyncio.wait(
							#
							[
								asyncio.create_task(ws.recv()),
								asyncio.create_task(shutdown_event.wait())
							],
							#
							return_when = asyncio.FIRST_COMPLETED,
							timeout		= ws_timeout_sec,
						)

						if not done:
							
							raise asyncio.TimeoutError()

						if hotswap_manager.is_shutting_down(): break
						
						for task in done:

							if (
								task is not None
								and not task.cancelled()
							):

								raw = task.result()
								break

						for task in pending: task.cancel()

						#———————————————————————————————————————————————————————
						# backup discards ws messages until it becomes main
						#———————————————————————————————————————————————————————

						if not is_active_conn: continue

						#———————————————————————————————————————————————————————
						# Message Ingestion
						#———————————————————————————————————————————————————————

						try:

							msg = orjson.loads(raw)
							stream = msg.get("stream", "")
							cur_symbol = (
								stream.split("@", 1)[0]
								or "UNKNOWN"
							).lower()

							if cur_symbol not in symbols:
								continue	# out of scope
							
							if (
								# drop if (gate closed) 
								# or (no mean latency available)
								(not event_stream_enable.is_set())
								or (mean_latency_dict[cur_symbol] == None)
							):
								continue

							data = msg.get("data", {})

							last_update = data.get("lastUpdateId")
							if last_update is None:
								continue

							bids = data.get("bids", [])
							asks = data.get("asks", [])

							#———————————————————————————————————————————————————————
							# SERVER TIMESTAMP RECONSTRUCTION FOR PARTIAL STREAMS
							#———————————————————————————————————————————————————————
							# Binance `@depth20@100ms` streams lack server timestamp
							# ("E"), unlike diff depth streams. We must estimate it
							# from local receipt time with delay corrections.
							#———————————————————————————————————————————————————————

							cur_time_ms = get_current_time_ms()

							if prev_snapshot_time_ms[cur_symbol] is not None:

								measured_interval_ms[cur_symbol] = (
									cur_time_ms
									- prev_snapshot_time_ms[cur_symbol]
								)
								prev_snapshot_time_ms[
									cur_symbol
								] = cur_time_ms

							else:

								prev_snapshot_time_ms[
									cur_symbol
								] = cur_time_ms

								continue

							put_snapshot_interval[cur_symbol].append(
								measured_interval_ms[cur_symbol]
							)

							#———————————————————————————————————————————————————————
							# Estimate Extra Timing
							#———————————————————————————————————————————————————————
							
							oneway_network_latency_ms = max(
								0, mean_latency_dict.get(
									cur_symbol, 0
								)
							)

							interval_delay_ms = max(0,
								measured_interval_ms[cur_symbol]
								- base_interval_ms
							)

							#———————————————————————————————————————————————————————

							snapshot = {
								#———————————————————————————————————————————————————
								# recv_ms: align with <symbol>@trade
								# net_delay_ms: side information
								# intv_lag_ms:  side information
								#———————————————————————————————————————————————————
								"last_update_id": last_update,
								#———————————————————————————————————————————————————
								"recv_ms":		  cur_time_ms,
								#———————————————————————————————————————————————————
								"net_delay_ms":	  oneway_network_latency_ms,
								#———————————————————————————————————————————————————
								"intv_lag_ms":	  interval_delay_ms,
								#———————————————————————————————————————————————————
								"bids": [
									[float(p), float(q)]
									for p, q in bids
								],
								#———————————————————————————————————————————————————
								"asks": [
									[float(p), float(q)]
									for p, q in asks
								],
								#———————————————————————————————————————————————————
							}

							#———————————————————————————————————————————————————————
							# `.qsize()` is less than or equal to one almost surely,
							# meaning that `snapshots_queue_dict` is being quickly
							# consumed via `.get()`.
							#———————————————————————————————————————————————————————
							
							await snapshots_queue_dict[
								cur_symbol
							].put(snapshot)

							#———————————————————————————————————————————————————————
							# 1st snapshot gate for FastAPI readiness
							#———————————————————————————————————————————————————————

							if not event_1st_snapshot.is_set():

								event_1st_snapshot.set()

							#———————————————————————————————————————————————————————
							# Statistics on WebSocket Receipt Interval
							#———————————————————————————————————————————————————————

							cur_time_ns = time.time_ns()

							if last_recv_time_ns is not None:
								
								websocket_recv_interval.append(
									(
										cur_time_ns - last_recv_time_ns
									) / 1_000_000_000.0
								)
								
							last_recv_time_ns = cur_time_ns

							ws_timeout_sec = update_ws_recv_timeout(
								websocket_recv_interval,
								websocket_recv_intv_stat,
								ws_timeout_multiplier,
								ws_timeout_default_sec,
								ws_timeout_min_sec,
							)

						except Exception as e:

							sym = (
								cur_symbol
								if cur_symbol in symbols
								else "UNKNOWN"
							)
							logger.warning(
								f"[{my_name()}][{sym.upper()}] "
								f"failed to process message: {e}",
								exc_info=True
							)
							continue  # stay in websocket loop

						finally:

							await hotswap_manager.cleanup_stale_tasks(
								refresh_period_sec
								+ hotswap_tolerance_sec,
								logger,
							)

					#———————————————————————————————————————————————————————————
					# No Messages even though WebSocket Alive
					#———————————————————————————————————————————————————————————

					except asyncio.TimeoutError:

						if hotswap_manager.is_shutting_down(): break

						ws_retry_cnt += 1
						
						logger.warning(
							f"[{my_name()}]\n"
							f"\tno data received for "
							f"{ws_timeout_sec:.6f}s\n"
							f"\tp90 ws.recv() intv.: "
							f"{websocket_recv_intv_stat['p90']:.6f}.\n"
							f"\t(ws_retry_cnt {ws_retry_cnt}) "
							f"reconnecting...",
							exc_info = False,
						)

						(
							#
							ws_retry_cnt,
							last_success_time
							#
						) = await calculate_backoff_and_sleep(
							#
							ws_retry_cnt, 
							last_success_time,
							#
						)

						break

					#———————————————————————————————————————————————————————————
					# WebSocket Interrupted
					#———————————————————————————————————————————————————————————

					except websockets.exceptions.ConnectionClosed as e:
						
						if hotswap_manager.is_shutting_down(): break
						
						ws_retry_cnt += 1
						
						logger.warning(
							f"[{my_name()}]\n"
							f"\tws connection closed: "
							f"{e.reason or 'no close frame'}\n"
							f"\t(ws_retry_cnt {ws_retry_cnt}) "
							f"reconnecting...",
							exc_info = False,
						)
						
						(
							#
							ws_retry_cnt,
							last_success_time
							#
						) = await calculate_backoff_and_sleep(
							#
							ws_retry_cnt,
							last_success_time,
							#
						)
						
						break

					#———————————————————————————————————————————————————————————
					# On (Ctrl + C)
					#———————————————————————————————————————————————————————————

					except asyncio.CancelledError:

						break 	# logging unnecessary

		#———————————————————————————————————————————————————————————————————————
		# On (Ctrl + C)
		#———————————————————————————————————————————————————————————————————————

		except asyncio.CancelledError:
			
			raise 	# logging unnecessary

		#———————————————————————————————————————————————————————————————————————
		# WebSocket Failure
		#———————————————————————————————————————————————————————————————————————

		except Exception as e:

			if hotswap_manager.is_shutting_down(): break

			# websocket-level error → exponential backoff + retry

			ws_retry_cnt += 1

			sym = (
				cur_symbol
				if cur_symbol in symbols
				else "UNKNOWN"
			)

			logger.warning(
				f"[{my_name()}]\n"
				f"\tws error: {e}\n"
				f"\t(ws_retry_cnt {ws_retry_cnt}) "
				f"reconnecting ...",
				exc_info = True,
			)

			(
				#
				ws_retry_cnt,
				last_success_time
				#
			) = await calculate_backoff_and_sleep(
				#
				ws_retry_cnt,
				last_success_time,
				#
			)

		#———————————————————————————————————————————————————————————————————————
		# Get to Know WebSocket Closed
		#———————————————————————————————————————————————————————————————————————

		finally:

			logger.info(
				f"[{my_name()}]📴 ws closed"
			)

#———————————————————————————————————————————————————————————————————————————————