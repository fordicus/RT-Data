# core.py

#———————————————————————————————————————————————————————————————————————————————

from util import (
	my_name,				# For exceptions with 0 Lebesgue measure
	NanoTimer,
	ms_to_datetime,
	format_ws_url,
	get_current_time_ms,
	get_global_log_queue,
	get_subprocess_logger
)

import sys, os, io, asyncio, json
import shutil, zipfile, logging
import websockets, time, random

from io import TextIOWrapper
from collections import OrderedDict
from typing import Optional
from concurrent.futures import ProcessPoolExecutor

#———————————————————————————————————————————————————————————————————————————————

#	 '2025-06-27_13-15'
# -> '2025-06-27'
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
):

	#——————————————————————————————————————————————————————————————

	def zip_and_remove(src_path: str):

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

		except Exception: raise

	#——————————————————————————————————————————————————————————————

	try:

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

			raise RuntimeError(
				f"File not found for compression: "
				f"{last_jsonl_path}"
			)

	except Exception as e:

		get_subprocess_logger().error(
			f"[{my_name()}][{symbol_upper}] "
			f"Failed to process {last_suffix}: {e}",
			exc_info=True
		)

#———————————————————————————————————————————————————————————————————————————————

def symbol_consolidate_a_day(
	symbol:	  str,
	day_str:  str,
	base_dir: str,
	purge:	  bool = True
):

	with NanoTimer() as timer:

		logger = get_subprocess_logger()

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

		# Abort early if directory is missing:
		# no data captured for this day

		if not os.path.isdir(tmp_dir):

			logger.error(
				f"[{my_name()}][{symbol.upper()}] "
				f"Temp dir missing on {day_str}: {tmp_dir}"
			)

			return

		# List all zipped minute-level files (may be empty)

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
						f"[{my_name()}][{symbol.upper()}] "
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

		# Recompress the consolidated .jsonl
		# into a final single-archive zip

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
	records_merged_dates:	dict[str, OrderedDict[str, None]],
	znr_executor:			ProcessPoolExecutor,
	records_znr_minutes:	dict[str, OrderedDict[str, None]],
	records_max:			int,
	logger:					logging.Logger,
):

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

	#———————————————————————————————————————————————————————————————————————————————

	def flush_snapshot(
		json_writer: TextIOWrapper,
		snapshot: dict,
		symbol: str,
		symbol_to_file_handles: dict[str, tuple[str, TextIOWrapper]],
		json_flush_interval: dict[str, int],
		latest_json_flush: dict[str, int],
		file_path: str,
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

	while True:

		#——————————————————————————————————————————————————————————————

		snapshot = await fetch_snapshot(queue, symbol)
		
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
		):

			logger.error(
				f"[{my_name()}][{symbol_upper}] "
				f"Failed to flush snapshot.",
				exc_info=True
			)

		del snapshot, file_path

#———————————————————————————————————————————————————————————————————————————————

from collections import deque

async def put_snapshot(		# @depth20@100ms
	snapshots_queue_dict:	dict[str, asyncio.Queue],
	event_stream_enable:	asyncio.Event,
	latency_dict:			dict[str, deque[int]],
	median_latency_dict:	dict[str, int],
	event_1st_snapshot:		asyncio.Event,
	max_backoff:			int, 
	base_backoff:			int,
	reset_cycle_after:		int,
	reset_backoff_level:	int,
	ws_url:					str,
	ws_ping_interval:		int,
	ws_ping_timeout:		int,
	symbols:				list,
	logger:					logging.Logger,
):

	"""————————————————————————————————————————————————————————————
	CORE FUNCTIONALITY:
		await snapshots_queue_dict[
			current_symbol
		].put(snapshot)
	———————————————————————————————————————————————————————————————
	HINT:
		asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
	————————————————————————————————————————————————————————————"""

	ws_retry_cnt = 0

	while True:

		current_symbol = "UNKNOWN"

		try:
			async with websockets.connect(
				ws_url,
				ping_interval = ws_ping_interval,
				ping_timeout  = ws_ping_timeout
			) as ws:

				logger.info(
					f"[put_snapshot] Connected to:\n"
					f"{format_ws_url(ws_url, '(depth20@100ms)')}\n"
				)

				ws_retry_cnt = 0

				async for raw in ws:
					try:
						msg	= json.loads(raw)
						stream = msg.get("stream", "")
						current_symbol = (
							stream.split("@", 1)[0]
							or "UNKNOWN"
						).lower()

						# out of scope
						if current_symbol not in symbols:
							continue

						# drop if (gate closed) 
						# or (no latency samples)
						if (
							(not event_stream_enable.is_set()) or
							(not latency_dict.get(
								current_symbol, [])
							)
						):
							continue

						data = msg.get("data", {})

						last_update = data.get("lastUpdateId")
						if last_update is None:
							continue

						bids = data.get("bids", [])
						asks = data.get("asks", [])

						#———————————————————————————————————————————————————————
						# Binance partial streams like `@depth20@100ms` do NOT
						# include the server-side event timestamp ("E"). Thus,
						# we must rely on local receipt time corrected by
						# estimated network latency and computation time among
						# coroutines.
						#———————————————————————————————————————————————————————
						# TODO: The difference between the current time and the
						# previous time right before defining `snapshot` is
						# expected to be 100ms. The difference higher than 100ms
						# is due to the computation time for the snapshot to be
						# defined within the whole main process, which much be
						# utilized to define `lat_ms`. The first `raw` must be
						# discarded to measure the difference and define 
						# `lat_ms`.
						#———————————————————————————————————————————————————————

						lat_ms = max(
							0, median_latency_dict.get(
								current_symbol, 0
							)
						)
						
						latency_adjusted_time = (
							get_current_time_ms() - lat_ms
						)

						snapshot = {
							"lastUpdateId": last_update,
							"eventTime": latency_adjusted_time,
							"bids": [
								[float(p), float(q)]
								for p, q in bids
							],
							"asks": [
								[float(p), float(q)]
								for p, q in asks
							],
						}

						#———————————————————————————————————————————————————————
						# `.qsize()` is less than or equal to one almost surely,
						# meaning that `snapshots_queue_dict` is being quickly
						# consumed via `.get()`.
						#———————————————————————————————————————————————————————
						
						await snapshots_queue_dict[
							current_symbol
						].put(snapshot)

						# 1st snapshot gate for FastAPI readiness
						
						if not event_1st_snapshot.is_set():
							event_1st_snapshot.set()

					except Exception as e:
						sym = (
							current_symbol
							if current_symbol in symbols
							else "UNKNOWN"
						)
						logger.warning(
							f"[put_snapshot][{sym.upper()}] "
							f"Failed to process message: {e}",
							exc_info=True
						)
						continue  # stay in websocket loop

		except asyncio.CancelledError:
			# propagate so caller can shut down gracefully
			raise

		except Exception as e:
			# websocket-level error → exponential backoff + retry
			ws_retry_cnt += 1
			sym = (
				current_symbol
				if current_symbol in symbols
				else "UNKNOWN"
			)

			logger.warning(
				f"[put_snapshot][{sym.upper()}] "
				f"WebSocket error "
				f"(ws_retry_cnt {ws_retry_cnt}): "
				f"{e}",
				exc_info=True
			)

			backoff = min(
				max_backoff, base_backoff * (2 ** ws_retry_cnt)
			) + random.uniform(0, 1)

			if ws_retry_cnt > reset_cycle_after:
				ws_retry_cnt = reset_backoff_level

			logger.warning(
				f"[put_snapshot][{sym.upper()}] "
				f"Retrying in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

		finally:

			#———————————————————————————————————————————————————————————————————
			# Informational close log; `async with` ensures ws is
			# closed. Use last known symbol purely for context
			# (may be UNKNOWN).
			#———————————————————————————————————————————————————————————————————

			sym = (
				current_symbol
				if current_symbol in symbols
				else "UNKNOWN"
			)
			logger.info(
				f"[put_snapshot][{sym.upper()}] "
				f"WebSocket connection closed."
			)

#———————————————————————————————————————————————————————————————————————————————