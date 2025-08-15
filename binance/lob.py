# core.py @2025-08-14 / DO NOT BLINDLY MODIFY THIS CODE

#———————————————————————————————————————————————————————————————————————————————

from util import (
	CMAP4TXT, RESET4TXT,
	my_name,
	get_ssl_context,
	NanoTimer,
	ms_to_datetime,
	update_shared_time_dict,
	compute_bias_ms,
	format_ws_url,
	get_current_time_ms,
	get_cur_datetime_str,
	get_global_log_queue,
	get_subprocess_logger,
	ensure_logging_on_exception,
	force_print_exception,
)

from hotswap import (
	HotSwapManager,
	hsm_schedule_backup,
	hsm_create_task,
)

from latency import (
	LatencyMonitor,
)

import sys, os, io, asyncio, orjson
import shutil, zipfile, logging
import websockets, time
import numpy as np
import math

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
	max_retries:  int   = 100,
	retry_delay:  float = 0.1,
	exp_backoff:  float = 1.2,
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
							exc_info = True,
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
				exc_info = True,
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
			exc_info = True,
		)
		raise

#———————————————————————————————————————————————————————————————————————————————

def proc_symbol_consolidate_a_day(
	symbol:		 str,
	day_str: 	 str,
	base_dir:	 str,
	purge:		 bool  = True,
	max_retries: int   = 100,
	retry_delay: float = 0.1,
	exp_backoff: float = 1.2,
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
				exc_info = True,
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
						exc_info = True,
					)

					return

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to open or write to merged file "
				f"{merged_path}: {e}",
				exc_info = True,
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
						exc_info = True,
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
					arcname = os.path.basename(merged_path),
				)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to compress merged "
				f"file on {day_str}: {e}",
				exc_info = True,
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
				exc_info = True,
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
					exc_info = True,
				)

		logger.info(
			f"[{my_name()}][{symbol.upper()}] "
			f"Successfully merged {len(zip_files)} files "
			f"for {day_str} (took {timer.tock():.5f} sec)."
		)

#———————————————————————————————————————————————————————————————————————————————

@ensure_logging_on_exception
async def symbol_dump_snapshot(
	#———————————————————————————————————————————————————————————————————————————
	symbol:					str,
	save_interval_min:		int,
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	lob_dir:				str,
	managed_fhndls:			dict[str, tuple[str, TextIOWrapper]],
	save_intv_monitor:		dict[str, deque[int]],
	purge_on_date_change:	int,
	merge_executor:			ProcessPoolExecutor,	# rollover (fire-and-forgat)
	znr_executor:			ProcessPoolExecutor,	# rollover (fire-and-forgat)
	records_max:			int,
	logger:					logging.Logger,
	shutdown_event:			asyncio.Event,
	file_sync_delay_sec:	float = 0.0005,
	#———————————————————————————————————————————————————————————————————————————
):

	#———————————————————————————————————————————————————————————————————————————

	def is_shutting_down():

		return shutdown_event.is_set()

	#———————————————————————————————————————————————————————————————————————————

	def safe_close_file_muted(
		f: TextIOWrapper
	):

		if f is not None and hasattr(f, 'close'):
			try:   f.close()
			except Exception: pass

	#———————————————————————————————————————————————————————————————————————————

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
				exc_info = True,
			)
			safe_close_file_muted(f)
			return False

	#———————————————————————————————————————————————————————————————————————————
	
	def refresh_file_handle(
		#———————————————————————————————————————————————————————————————————————
		file_path:		str,
		suffix:			str,
		symbol:			str,
		managed_fhndls: dict[str, tuple[str, TextIOWrapper]],
		#———————————————————————————————————————————————————————————————————————
	) -> Optional[TextIOWrapper]:

		try:

			json_writer = open(
				file_path, "a",
				encoding = "utf-8",
			)

		except OSError as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Open failed: {file_path} → {e}",
				exc_info = True,
			)
			return None

		if json_writer is not None:

			try:

				managed_fhndls[symbol] = (
					suffix, json_writer,
				)

			except Exception as e:

				logger.error(
					f"[{my_name()}][{symbol.upper()}] "
					f"Failed to assign file handle: "
					f"{file_path} → {e}",
					exc_info = True,
				)
				safe_close_jsonl(json_writer)
				return None

		return json_writer

	#———————————————————————————————————————————————————————————————————————————

	def pop_and_close_handle(
		handles: dict[str, tuple[str, TextIOWrapper]],
		symbol:  str,
	):

		try:

			tup = handles.pop(symbol, None)			# not only `pop` from dict
			if tup is not None:
				safe_close_file_muted(tup[1])		# but also `close`

		except Exception: pass

	#———————————————————————————————————————————————————————————————————————————

	async def fetch_snapshot(
		#———————————————————————————————————————————————————————————————————————
		queue:  asyncio.Queue,
		symbol: str,
		#———————————————————————————————————————————————————————————————————————
	) -> Optional[dict]:

		try:

			return await queue.get()
		
		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to get snapshot from queue: {e}",
				exc_info = True,
			)
			return None

	#———————————————————————————————————————————————————————————————————————————

	def get_file_suffix(
		#———————————————————————————————————————————————————————————————————————
		interval_min: int,
		event_ts_ms:  int,
		#———————————————————————————————————————————————————————————————————————
	) -> str:

		try:

			ts = ms_to_datetime(event_ts_ms)

			if interval_min < 1440:

				return ts.strftime("%Y-%m-%d_%H-%M")

			else:

				return ts.strftime("%Y-%m-%d")

		except Exception as e:

			logger.error(
				f"[{my_name()}] Failed to generate suffix for "
				f"interval_min={interval_min}, "
				f"event_ts_ms={event_ts_ms}: {e}",
				exc_info = True,
			)

			return "invalid_suffix"

	#———————————————————————————————————————————————————————————————————————————

	def get_suffix_n_date(
		#———————————————————————————————————————————————————————————————————————
		save_interval_min: int,
		snapshot:		   dict,
		symbol:			   str,
		#———————————————————————————————————————————————————————————————————————
	) -> tuple[Optional[str], Optional[str]]:
		
		try:

			suffix = get_file_suffix(
				save_interval_min,
				snapshot.get("recv_ms"),		# align with <symbol>@aggTrade
			)

			date_str = get_date_from_suffix(suffix)

			return (suffix, date_str)
		
		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Failed to compute suffix/day: {e}",
				exc_info = True,
			)

			return (None, None)

	#———————————————————————————————————————————————————————————————————————————

	async def gen_file_path(
		#———————————————————————————————————————————————————————————————————————
		symbol_upper: str,
		suffix:		  str,
		lob_dir:	  str,
		date_str:	  str,
		#———————————————————————————————————————————————————————————————————————
	) -> Optional[str]:
		
		try:

			file_name = f"{symbol_upper}_orderbook_{suffix}.jsonl"
			temp_dir  = os.path.join(lob_dir, "temporary",
				f"{symbol_upper}_orderbook_{date_str}",
			)
			await asyncio.to_thread(
				os.makedirs,
				temp_dir,
				exist_ok = True,
			)
			return os.path.join(temp_dir, file_name)

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to build file path: {e}",
				exc_info = True,
			)
			return None

	#———————————————————————————————————————————————————————————————————————————

	def flush_snapshot(
		#———————————————————————————————————————————————————————————————————————
		json_writer:		TextIOWrapper,
		snapshot:			dict,
		symbol:				str,
		managed_fhndls:		dict[str, tuple[str, TextIOWrapper]],
		save_intv_monitor:	dict[str, deque[int]],
		latest_json_flush:	int,
		file_path:			str,
		#———————————————————————————————————————————————————————————————————————
	) -> tuple[
		bool,	# success flag
		int,	# latest_json_flush
	]:

		try:

			if json_writer.closed:
				
				if is_shutting_down():

					return (True, latest_json_flush)

				else:

					logger.warning(
						f"[{my_name()}][{symbol.upper()}] "
						f"attempted to write to closed file: "
						f"{file_path}"
					)

					return (False, latest_json_flush)

			json_writer.write(
				orjson.dumps(snapshot).decode() + "\n"
			)
			json_writer.flush()

			cur_time_ms = get_current_time_ms()

			save_intv_monitor[symbol].append(
				cur_time_ms - latest_json_flush
			)
			
			latest_json_flush = cur_time_ms

			return (True, latest_json_flush)

		except ValueError as e:

			if "closed file" in str(e):
				
				return (False, latest_json_flush)

			else: raise  # Propagate any other ValueError

		except Exception as e:

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"write failed: {file_path} → {e}",
				exc_info = True,
			)

			try:

				# Invalidate `json_writer` for next iteration

				pop_and_close_handle(
					managed_fhndls, symbol
				)

			except Exception: pass

			return (False, latest_json_flush)

	#———————————————————————————————————————————————————————————————————————————

	def memorize_treated(
		#———————————————————————————————————————————————————————————————————————
		records:	 OrderedDict[str, None],
		records_max: int,
		symbol:		 str,
		to_rec:		 str,
		#———————————————————————————————————————————————————————————————————————
	):

		try:

			# discard the oldest at the front of the container
			if len(records) >= records_max:
				records.popitem(last = False)
			records[to_rec] = None

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to memorize treated record "
				f"for symbol='{symbol}', to_rec='{to_rec}': {e}"
			) from e

	#———————————————————————————————————————————————————————————————————————————

	queue				= snapshots_queue_dict[symbol]
	symbol_upper		= symbol.upper()
	latest_json_flush	= get_current_time_ms()
	merged_dates_record = OrderedDict()
	znr_minutes_record	= OrderedDict()
	
	last_snapshot_time_ms = None		# checks timestamp order reversal

	try:

		while not is_shutting_down():	# infinite standalone loop

			#———————————————————————————————————————————————————————————————————

			snapshot = await fetch_snapshot(queue, symbol)
			
			if snapshot is None:
				logger.critical(
					f"[{my_name()}][{symbol_upper}] "
					f"snapshot is None, skipping iteration."
				)
				continue
			
			suffix, date_str = get_suffix_n_date(
				save_interval_min,
				snapshot, symbol,
			)

			if ((suffix is None) or (date_str is None)):
				logger.critical(
					f"[{my_name()}][{symbol_upper}] "
					f"suffix or date string is None, "
					f"skipping iteration."
				)
				continue

			file_path = await gen_file_path(
				symbol_upper, suffix,
				lob_dir, date_str,
			)
			
			if file_path is None:
				logger.critical(
					f"[{my_name()}][{symbol_upper}] "
					f"file path is None, "
					f"skipping iteration."
				)
				continue

			#───────────────────────────────────────────────────────────────────
			# STEP 1: Roll-over by Minute
			#───────────────────────────────────────────────────────────────────
			# `last_suffix` will be `None` at the beginning.
			#───────────────────────────────────────────────────────────────────

			(
				#
				last_suffix,
				json_writer,
				#
			) = managed_fhndls.get(symbol,
				#
				(None, None),
				#
			)

			if last_suffix != suffix:

				if json_writer:							# if not the first flush

					# ──────────────────────────────────────────────────────────

					if not safe_close_jsonl(json_writer):

						logger.warning(
							f"[{my_name()}][{symbol.upper()}] "
							f"JSON writer may not "
							f"have been closed."
						)

					del json_writer

					# ──────────────────────────────────────────────────────────
					# fire and forget
					# ──────────────────────────────────────────────────────────

					await asyncio.sleep(file_sync_delay_sec)

					if last_suffix not in znr_minutes_record:

						memorize_treated(
							znr_minutes_record,
							records_max,
							symbol, last_suffix,
						)

						znr_executor.submit(# pickle
							proc_zip_n_remove_jsonl,
							lob_dir, symbol_upper, 
							last_suffix,
						)

				# ──────────────────────────────────────────────────────────────

				try: 
					
					json_writer = refresh_file_handle(
						file_path, suffix, symbol, 
						managed_fhndls,
					)
					if json_writer is None: continue 

				except Exception as e:

					logger.error(
						f"[{my_name()}][{symbol_upper}] "
						f"Failed to refresh file handles → {e}",
						exc_info = True,
					)
					continue

			#───────────────────────────────────────────────────────────────────
			# STEP 2: Check for day rollover and trigger merge
			# At this point, ALL previous files are guaranteed to be .zip
			#───────────────────────────────────────────────────────────────────

			try:

				if last_suffix:

					last_date = get_date_from_suffix(last_suffix)

					if ((last_date != date_str) and 
						(last_date not in merged_dates_record)
					):

						memorize_treated(
							merged_dates_record,
							records_max,
							symbol, last_date,
						)
						
						merge_executor.submit(	# pickle
							proc_symbol_consolidate_a_day,
							symbol, last_date, lob_dir,
							purge = (purge_on_date_change == 1),
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
					exc_info = True,
				)

				if 'last_date' in locals(): del last_date
				del e
				continue

			finally:

				del date_str, last_suffix

			#───────────────────────────────────────────────────────────────────
			# STEP 3: Write snapshot to file and update flush intervals
			#───────────────────────────────────────────────────────────────────

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

			#───────────────────────────────────────────────────────────────────

			(
				#───────────────────────────────────────────────────────────────
				is_success,
				latest_json_flush,
				#───────────────────────────────────────────────────────────────
			) = flush_snapshot(
				#───────────────────────────────────────────────────────────────
				json_writer,
				snapshot,
				symbol,
				managed_fhndls,
				save_intv_monitor,
				latest_json_flush,
				file_path,
				#───────────────────────────────────────────────────────────────
			)

			if not is_success:

				logger.critical(
					f"[{my_name()}][{symbol_upper}] "
					f"failed to flush snapshot.",
					exc_info = True,
				)

			# await asyncio.sleep(1)		# when simulating some delays

			del snapshot, file_path, is_success

	except asyncio.CancelledError:

		raise # logging unnecessary

	except Exception as e:

		logger.error(
			f"[{my_name()}][{symbol_upper}] unexpected error: {e}"
		)

	finally:

		logger.info(f"[{my_name()}][{symbol_upper}] task ends")

#———————————————————————————————————————————————————————————————————————————————

















































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
	put_snapshot_interval:				dict[str, deque[int]],
	#———————————————————————————————————————————————————————————————————————————
	# Datafication
	#———————————————————————————————————————————————————————————————————————————
	snapshots_queue_dict:				dict[str, asyncio.Queue],
	#———————————————————————————————————————————————————————————————————————————
	# Latency Control
	#———————————————————————————————————————————————————————————————————————————
	lat_mon:							LatencyMonitor,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Recovery
	#———————————————————————————————————————————————————————————————————————————
	shared_time_dict:					dict[str, float],
	shared_time_dict_key:				str,
	min_reconn_sec:						float,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Peer
	#———————————————————————————————————————————————————————————————————————————
	ws_url:								dict[str, str],
	ws_url_key:							str,									# manage keys better
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
	shutdown_event:						asyncio.Event,
	handoff_event:						Optional[asyncio.Event] = None,
	is_backup:							bool = False,
	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Liveness Control
	#———————————————————————————————————————————————————————————————————————————
	base_interval_ms:					int	  = 100,
	ws_timeout_multiplier:				float =	  8.0,
	ws_timeout_default_sec:				float =	 10.0,
	ws_timeout_min_sec:					float =	  5.0,
	ws_recv_intv_len_per_sym:			int	  =	  100,
	#———————————————————————————————————————————————————————————————————————————
):

	"""—————————————————————————————————————————————————————————————————————————
	HINT:
		asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
	—————————————————————————————————————————————————————————————————————————"""

	async def sleep_on_ws_reconn(
		shared_time_dict:	  dict[str, float],
		shared_time_dict_key: str,
		min_reconn_sec:		  float,
		logger:				  logging.Logger,
	):

		#———————————————————————————————————————————————————————————————————————
		# Websocket (re)connection attempt requires at minimum 1.0s
		# after each trial (https://tinyurl.com/BinanceWsMan);
		# exponential backoff unnecessary
		#———————————————————————————————————————————————————————————————————————

		try:

			since_the_latest_sleep = (
				time.time() - shared_time_dict[shared_time_dict_key]
			)

			if (
				since_the_latest_sleep 
				>= min_reconn_sec
			):

				backoff = 0.0

			else:

				backoff = (
					min_reconn_sec
					- since_the_latest_sleep
				)
				
			await asyncio.sleep(backoff)

		except Exception as e:

			logger.critical(
				f"[{my_name()}] {e}"
			)
			raise

	#———————————————————————————————————————————————————————————————————————————

	def reset_ws_recv_intv_state(
		websocket_recv_intv_stat: dict[str, float | None],
		websocket_recv_interval:  deque[float],
		last_recv_time_ns:		  Optional[float],
	) -> Optional[float]:

		websocket_recv_intv_stat['p90'] = None
		websocket_recv_interval.clear()
		last_recv_time_ns = None
		
		return last_recv_time_ns

	#———————————————————————————————————————————————————————————————————————————

	def update_ws_recv_timeout(		# to detect websockets with no data
		data:			deque[float],
		stat:			dict[str, float | None],
		multiplier:		float,
		default:		float,
		minimum:		float,
		*,
		max_cap:		float	= 10.0,
	) -> float:			# ws_timeout_sec (adaptive based on statistics)
		
		finite = [
			x for x in data 
			if (
				math.isfinite(x)
				and x >= 0.0
			)
		]

		if len(finite) >= data.maxlen:
			
			p90 = float(np.percentile(finite, 90))
			stat['p90'] = p90
			cand = max(p90 * multiplier, minimum)
			
			return min(cand, max_cap)
			
		else:
			
			
			stat['p90'] = None
			return max(default, minimum)

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
	standby_reported = False

	#———————————————————————————————————————————————————————————————————————————
	# WebSocket Liveness Control
	#———————————————————————————————————————————————————————————————————————————

	ws_retry_cnt = 0
	ws_timeout_sec = ws_timeout_default_sec
	last_recv_time_ns = None

	websocket_recv_intv_stat: dict[str, float | None] = {"p90": None}
	websocket_recv_interval:  deque[float] = deque(
		maxlen = (
			len(symbols) *
			ws_recv_intv_len_per_sym
		)
	)
	
	measured_interval_ms: dict[str, Optional[int]] = {}
	measured_interval_ms.clear()
	measured_interval_ms.update({
		symbol: None
		for symbol in symbols
	})
	
	prev_snapshot_time_ms: dict[str, Optional[int]] = {}
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

			target_port, cur_port_index = hotswap_manager.\
				cycle_port_number(
					ports_stream_binance_com,
				)

			ws_url_complete = ws_url[ws_url_key].replace(
				wildcard_stream_binance_com_port,
				target_port,
			)

			#———————————————————————————————————————————————————————————————————
			# Within WebSocket
			#———————————————————————————————————————————————————————————————————

			async with websockets.connect(
				ws_url_complete,
				ssl			  = get_ssl_context(),
				ping_interval = ws_ping_interval,
				ping_timeout  = ws_ping_timeout,
				compression	  = None,
			) as ws:

				#———————————————————————————————————————————————————————————————
				# Controlled (Re)connection
				#———————————————————————————————————————————————————————————————

				update_shared_time_dict(
					shared_time_dict,
					shared_time_dict_key,
				)	# upon successful ws (re)connection

				ws_retry_cnt = 0
				ws_start_time = time.time()

				ws_url_to_prt = format_ws_url(
					ws_url_complete,
					symbols,
					ports_stream_binance_com,
				)

				last_recv_time_ns = reset_ws_recv_intv_state(
					websocket_recv_intv_stat,
					websocket_recv_interval,
					last_recv_time_ns,
				)

				#———————————————————————————————————————————————————————————————

				logger.info(
					f"[{my_name()}]🟢\n  "
					f"{ws_url_to_prt}"
				)

				#———————————————————————————————————————————————————————————————
				# [HotSwap] backup standby
				#———————————————————————————————————————————————————————————————

				if (
					is_backup
					and handoff_event
					and len(ports_stream_binance_com) > 1
				):

					if not standby_reported:

						logger.info(f"[{my_name()}]🕒 backup standby")
						standby_reported = True

				#———————————————————————————————————————————————————————————————
				# [HotSwap] initial main: prepare a backup
				#———————————————————————————————————————————————————————————————

				elif (
					not is_backup
					and not hotswap_prepared
					and len(ports_stream_binance_com) > 1
				):

					hotswap_prepared = True

					hsm_create_task(hotswap_manager,
						hsm_schedule_backup(
							#———————————————————————————————————————————————————
							hotswap_manager,
							backup_start_time,
							#———————————————————————————————————————————————————
							lambda _event, _is_backup: wrapped_put_snapshot(
								#———————————————————————————————————————
								put_snapshot_interval,
								#———————————————————————————————————————
								snapshots_queue_dict,
								#———————————————————————————————————————
								lat_mon,
								#———————————————————————————————————————
								shared_time_dict,
								shared_time_dict_key,
								min_reconn_sec,
								#———————————————————————————————————————
								ws_url,
								ws_url_key,
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
								_event,
								_is_backup,
								#———————————————————————————————————————
							),
							#———————————————————————————————————————————————————
							logger,
							back_up_ready_ahead_sec,
							ws_start_time,
							#———————————————————————————————————————————————————
						),
						name = f"put_snapshot() @{get_cur_datetime_str()}",
					)

					logger.info(
						f"[{my_name()}]📅 initial backup scheduled"
					)

				#———————————————————————————————————————————————————————————————
				# loop inside ws
				#———————————————————————————————————————————————————————————————

				while not hotswap_manager.is_shutting_down():

					#———————————————————————————————————————————————————————————
					# [HotSwap] backup → main
					#———————————————————————————————————————————————————————————

					if (
						is_backup
						and not is_active_conn
						and handoff_event
						and handoff_event.is_set()
						and len(ports_stream_binance_com) > 1
					):

						#———————————————————————————————————————————————————————
						# awaiting handoff event trigger: backup → main
						#———————————————————————————————————————————————————————
						
						is_active_conn = True

						logger.info(f"[{my_name()}]🔥 backup → main")

						#———————————————————————————————————————————————————————
						# prepare the next backup
						#———————————————————————————————————————————————————————

						hsm_create_task(hotswap_manager,
							hsm_schedule_backup(
								#———————————————————————————————————————————————
								hotswap_manager,
								backup_start_time,
								#———————————————————————————————————————————————
								lambda _event, _is_backup: wrapped_put_snapshot(
									#———————————————————————————————————————————
									put_snapshot_interval,
									#———————————————————————————————————————————
									snapshots_queue_dict,
									#———————————————————————————————————————————
									lat_mon,
									#———————————————————————————————————————————
									shared_time_dict,
									shared_time_dict_key,
									min_reconn_sec,
									#———————————————————————————————————————————
									ws_url,
									ws_url_key,
									wildcard_stream_binance_com_port,
									ports_stream_binance_com,
									ws_ping_interval,
									ws_ping_timeout,
									#———————————————————————————————————————————
									symbols,
									logger,
									#———————————————————————————————————————————
									port_cycling_period_hrs,
									back_up_ready_ahead_sec,
									hotswap_manager,
									shutdown_event,
									_event,
									_is_backup,
									#———————————————————————————————————————————
								),
								#———————————————————————————————————————————————
								logger,
								back_up_ready_ahead_sec,
								ws_start_time,
								#———————————————————————————————————————————————
							),
							name = f"put_snapshot() @{get_cur_datetime_str()}",
						)

						hotswap_manager.handoff_completed = False
						
						logger.info(
							f"[{my_name()}]📅 next backup scheduled"
						)

					#———————————————————————————————————————————————————————————
					# [HotSwap] main: commence hotswap
					#———————————————————————————————————————————————————————————
					
					elif (
						is_active_conn
						and not hotswap_manager.is_shutting_down()
						and (time.time() - ws_start_time) >= refresh_period_sec
						and len(ports_stream_binance_com) > 1
					):

						#———————————————————————————————————————————————————————
						
						if hotswap_manager.is_ready_for_handoff():

							#———————————————————————————————————————————————————

							try:

								logger.info(
									f"[{my_name()}]🔄 hotswap starts"
								)

								with NanoTimer() as timer:

									await hotswap_manager.commit_hotswap(
										logger,
									)

									logger.info(
										f"[{my_name()}]✅ hotswap done"
										f" in {timer.tock() * 1000.:.3f} ms"
									)

								#———————————————————————————————————————————————

								if hotswap_manager.handoff_completed:

									is_active_conn = False

									if (
										asyncio.current_task()
										in hotswap_manager.hotswap_tasks
									):

										hotswap_manager.hotswap_tasks.remove(
											asyncio.current_task()
										)
										
									return	# main returns

								#———————————————————————————————————————————————

								else:	# hotswap should have been completed

									raise RuntimeError(
										f"hotswap failed @main task"
									)

							#———————————————————————————————————————————————————

							except Exception as e:

								logger.critical(
									f"[{my_name()}] "
									f"{e}; task terminates",
									exc_info = True,
								)
								hotswap_prepared = False

						#———————————————————————————————————————————————————————

						else:

							logger.info(
								f"[{my_name()}] backup not yet ready; "
								f"will be prepared in the next loop."
							)
							hotswap_prepared = False

					#———————————————————————————————————————————————————————————
					# Messages within WebSocket
					#———————————————————————————————————————————————————————————
					
					try:

						#———————————————————————————————————————————————————————
						# Receive a Message or Shutting Down
						#———————————————————————————————————————————————————————
						
						recv_task	  = asyncio.create_task(ws.recv())
						shutdown_task = asyncio.create_task(
							shutdown_event.wait()
						)

						done, pending = await asyncio.wait(
							[
								recv_task, shutdown_task
							],
							return_when = asyncio.FIRST_COMPLETED,
							timeout = ws_timeout_sec,
						)

						if not done:		   # timeout

							for t in pending: t.cancel()
							raise asyncio.TimeoutError()

						if shutdown_task in done:

							for t in pending: t.cancel()
							return

						# `recv_task` is done
						raw = recv_task.result()
						for t in pending: t.cancel()

						#———————————————————————————————————————————————————————
						# Message Ingestion
						#———————————————————————————————————————————————————————

						try:

							msg = orjson.loads(raw)

							#———————————————————————————————————————————————————
							# Validate: <symbol>@depth20@100ms
							#———————————————————————————————————————————————————

							stream = msg.get("stream", "")
							split  = stream.split("@")

							if len(split) != 3:

								raise ValueError(
									f"unexpected "
									f"stream: {stream}"
								)

							if split[1] != "depth20":

								raise ValueError(
									f"expected `depth20` but"
									f"received {split[1]}; "
								)

							if split[2] != "100ms":

								raise ValueError(
									f"expected `100ms` but"
									f"received {split[2]}; "
								)

							cur_symbol = (
								split[0]
								or "UNKNOWN"
							).lower()

							if cur_symbol not in symbols:

								raise ValueError(
									f"unexpected "
									f"symbol: {cur_symbol.upper()}"
								)

							del split

							#———————————————————————————————————————————————————
							# Process the `data` Field
							#———————————————————————————————————————————————————

							data = msg.get("data", {})
							bids = data.get("bids")
							asks = data.get("asks")

							if data.get("lastUpdateId") is None:

								raise ValueError(
									f"missing `lastUpdateId` @data"
								)

							if ((bids is None) or (asks is None)):

								raise ValueError(
									f"missing `bids` or `asks` @data"
								)

							del data

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

							#———————————————————————————————————————————————————
							# no latency available
							# or a backup connection
							#———————————————————————————————————————————————————
							
							if (
								lat_mon.latency[cur_symbol] is None
								or not is_active_conn
							):

								continue

							oneway_network_latency_ms = max(
								0, lat_mon.latency.get(
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
								# recv_ms:		align with <symbol>@aggTrade
								# net_delay_ms: side information
								# intv_lag_ms:  side information
								#———————————————————————————————————————————————————
								"recv_ms":		  cur_time_ms,
								"net_delay_ms":	  oneway_network_latency_ms,
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

							if not lat_mon.evnt_1st_dom.is_set():

								lat_mon.evnt_1st_dom.set()

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
								exc_info = True,
							)
							continue  	# stay in the websocket loop

					#———————————————————————————————————————————————————————————
					# No Messages or WebSocket Closed → Backoff + Retry
					#———————————————————————————————————————————————————————————

					except asyncio.TimeoutError as e:

						if hotswap_manager.is_shutting_down(): break

						ws_retry_cnt += 1

						p90 = websocket_recv_intv_stat.get('p90')
						p90_ms_str = (
							f"{p90 * 1000.0:.2f}ms"
							if (
								isinstance(p90, (int, float))
								and math.isfinite(p90)
							)
							else "n/a"
						)
						reason = (
							f"no data received for "
							f"{ws_timeout_sec:.2f}s; "
							f"p90 recv intv {p90_ms_str}"
						)

						logger.warning(
							f"[{my_name()}] {reason} / "
							f"reconnecting: {ws_retry_cnt}",
							exc_info = False,
						)

						await sleep_on_ws_reconn(
							shared_time_dict,
							shared_time_dict_key,
							min_reconn_sec,
							logger,
						)

						break

					except websockets.exceptions.ConnectionClosed as e:

						if hotswap_manager.is_shutting_down(): break

						ws_retry_cnt += 1

						is_ok = isinstance(e,
							websockets.exceptions.ConnectionClosedOK
						)
						
						close_reason = (
							getattr(e, "reason", None)
							or "no close frame"
						)
						close_code = getattr(e, "code", None)

						reason = (
							f"ws connection closed: "
							f"code={close_code}, "
							f"reason={close_reason}"
						)

						log = (
							logger.info if is_ok
							else logger.warning
						)

						log(
							f"[{my_name()}] {reason} / "
							f"reconnecting: {ws_retry_cnt}",
							exc_info = False,
						)

						await sleep_on_ws_reconn(
							shared_time_dict,
							shared_time_dict_key,
							min_reconn_sec,
							logger,
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
		# WebSocket Failure → Backoff + Retry
		#———————————————————————————————————————————————————————————————————————

		except Exception as e:

			if hotswap_manager.is_shutting_down(): break

			ws_retry_cnt += 1

			logger.warning(
				f"[{my_name()}] ws error: {e} / "
				f"reconnecting: {ws_retry_cnt}",
				exc_info = True,
			)

			await sleep_on_ws_reconn(
				shared_time_dict,
				shared_time_dict_key,
				min_reconn_sec,
				logger,
			)

		#———————————————————————————————————————————————————————————————————————
		# Get to Know WebSocket Closed
		#———————————————————————————————————————————————————————————————————————

		finally:

			if (
				asyncio.current_task()
				in hotswap_manager.hotswap_tasks
			):

				hotswap_manager.hotswap_tasks.remove(
					asyncio.current_task()
				)

			logger.info(
				f"[{my_name()}]📴 ws closed / "
				f"len(hotswap_tasks): "
				f"{CMAP4TXT.get('CYBER TEAL')}"
				f"{len(hotswap_manager.hotswap_tasks)}"
				f"{RESET4TXT}"
			)

#———————————————————————————————————————————————————————————————————————————————