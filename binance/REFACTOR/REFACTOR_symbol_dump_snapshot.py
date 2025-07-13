async def symbol_dump_snapshot(symbol: str) -> None:

	""" ————————————————————————————————————————————————————————————————
	CORE FUNCTIONALITY:
		TO BE WRITTEN
	————————————————————————————————————————————————————————————————————
	GLOBAL VARIABLES:
		READ:
			SNAPSHOTS_QUEUE_DICT:	dict[str, asyncio.Queue]
			EVENT_STREAM_ENABLE:	asyncio.Event
			LOB_DIR:				str
		WRITE:
			JSON_FLUSH_INTERVAL:	Dict[str, int]
		READ & WRITE:
			SYMBOL_TO_FILE_HANDLES: dict[str, tuple[str, TextIOWrapper]]
			LATEST_JSON_FLUSH:		Dict[str, int]
	————————————————————————————————————————————————————————————————————
	HINT:
		1. KYC (Know-Your-Cycle) protocol:
			`del local`: refcount ↓, GC runs sooner
		2. It is intended to trigger `continue` within the while loop 
			upon any exception; this allows us to invalidate the data
			being collected so that we can identify and resolve the
			issue before resuming the data collection pipeline.
	———————————————————————————————————————————————————————————————— """

	def safe_close_file(f: TextIOWrapper):
		""" ————————————————————————————————————————————————————————————
		# from io import TextIOWrapper
		#	if 'file' in locals():
		#		safe_close_file(file)
		#		del file
		———————————————————————————————————————————————————————————— """
		if f is not None and hasattr(f, 'close'):
			try:
				f.close()
			except Exception:
				pass

	def pop_and_close_handle(
		handles: dict[str, tuple[str, TextIOWrapper]], symbol: str
	):
		tup = handles.pop(symbol, None)
		if tup is not None:
			safe_close_file(tup[1])

	queue = SNAPSHOTS_QUEUE_DICT[symbol]
	symbol_upper = symbol.upper()

	while True:

		try:

			snapshot = await queue.get()

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol_upper}] "
				f"Failed to get snapshot from queue: {e}",
				exc_info=True
			)

			if 'snapshot' in locals(): del snapshot
			del e
			continue

		if not EVENT_STREAM_ENABLE.is_set():
			continue

		try:

			suffix = get_file_suffix(
				SAVE_INTERVAL_MIN,
				snapshot.get(
					"eventTime",
					get_current_time_ms()
				)
			)

			day_str = get_date_from_suffix(suffix)

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol_upper}] "
				f"Failed to compute suffix/day: {e}",
				exc_info=True
			)

			_locals_ = locals()
			for var in ['suffix', 'day_str']:
				if var in _locals_: del _locals_[var]
			del _locals_, e
			continue

		# ── Build file name and full path

		try:

			filename = f"{symbol_upper}_orderbook_{suffix}.jsonl"
			tmp_dir = os.path.join(LOB_DIR, "temporary",
				f"{symbol_upper}_orderbook_{day_str}",
			)
			os.makedirs(tmp_dir, exist_ok=True)
			file_path = os.path.join(tmp_dir, filename)

			del filename, tmp_dir

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol_upper}] "
				f"Failed to build file path: {e}",
				exc_info=True
			)

			_locals_ = locals()
			for var in [
				'file_path', 'filename', 'tmp_dir', 'suffix', 'day_str'
			]:
				if var in _locals_: del _locals_[var]
			del _locals_, e
			continue

		# ────────────────────────────────────────────────────────────────────
		# STEP 1
		# 	zip_and_remove(last_file_path)
		#	json_writer = open(file_path, "a", encoding="utf-8")
		# ────────────────────────────────────────────────────────────────────

		last_suffix, json_writer = SYMBOL_TO_FILE_HANDLES.get(
			symbol, (None, None))

		if last_suffix != suffix:

			if json_writer:

				try: json_writer.close()

				except Exception as e:

					logger.error(f"[symbol_dump_snapshot]"
						f"[{symbol_upper}] Close failed → {e}",
						exc_info=True
					)
					del e

				finally:
					
					if 'json_writer' in locals():
						safe_close_file(json_writer)
						del json_writer

				try:

					last_file_path = os.path.join(
						os.path.join(
							LOB_DIR, "temporary",
							f"{symbol_upper}_orderbook_"
							f"{get_date_from_suffix(last_suffix)}",
						),
						f"{symbol_upper}_orderbook_{last_suffix}.jsonl"
					)

					does_last_file_exist = os.path.exists(last_file_path)

					if does_last_file_exist:

						zip_and_remove(last_file_path)

					else:

						logger.error(
							f"[symbol_dump_snapshot][{symbol_upper}] "
							f"File not found for compression: "
							f"{last_file_path}"
						)

					del last_file_path, does_last_file_exist

				except Exception as e:

					logger.error(
						f"[symbol_dump_snapshot][{symbol_upper}] "
						f"zip_and_remove(last_file_path={last_file_path}) "
						f"failed for last_suffix={last_suffix}: {e}",
						exc_info=True
					)

					if 'last_file_path' in locals(): del last_file_path
					del e

			try: 
				
				json_writer = open(
					file_path, "a", encoding="utf-8"
				)	# for the current snapshot

			except OSError as e:

				logger.error(
					f"[symbol_dump_snapshot][{symbol_upper}] "
					f"Open failed: {file_path} → {e}",
					exc_info=True
				)

				_locals_ = locals()
				for var in ['file_path', 'last_suffix', 'json_writer']:
					if var in _locals_: del _locals_[var]
				del _locals_, e
				continue

			SYMBOL_TO_FILE_HANDLES[symbol] = (suffix, json_writer)

		# ────────────────────────────────────────────────────────────────────
		# 🔧 STEP 2: Check for day rollover and trigger merge
		# At this point, ALL previous files are guaranteed to be .zip
		# ────────────────────────────────────────────────────────────────────

		try:

			if last_suffix:

				last_day = get_date_from_suffix(last_suffix)

				with MERGE_LOCKS[symbol]:

					# ────────────────────────────────────────────────────────
					# This block ensures thread-safe execution for
					# merge operations. All previous files are now .zip
					# format, ensuring complete day consolidation.
					# ────────────────────────────────────────────────────────

					if ((last_day != day_str) and 
						(last_day not in MERGED_DAYS[symbol])
					):

						MERGED_DAYS[symbol].add(last_day)
						
						symbol_trigger_merge(symbol, last_day)

						logger.info(
							f"[symbol_dump_snapshot][{symbol_upper}] "
							f"Triggered merge for {last_day} "
							f"(current day: {day_str})."
						)

						del last_day

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol_upper}] "
				f"Failed to check/trigger merge: {e}",
				exc_info=True
			)

			if 'last_day' in locals(): del last_day
			del e
			continue

		finally:

			del day_str, last_suffix

		try:

			json_writer.write(
				json.dumps(snapshot, 
					separators=(",", ":")
				) + "\n"
			)
			json_writer.flush()

			current_time = get_current_time_ms()

			JSON_FLUSH_INTERVAL[symbol] = (
				current_time - LATEST_JSON_FLUSH[symbol]
			)
			
			LATEST_JSON_FLUSH[symbol] = current_time

			del current_time

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol_upper}] "
				f"Write failed: {file_path} → {e}",
				exc_info=True
			)

			try:

				# Invalidate `json_writer` for next iteratio
				pop_and_close_handle(SYMBOL_TO_FILE_HANDLES, symbol)

			except Exception:
				pass

			if 'current_time' in locals(): del current_time
			del e
			continue

		finally:

			_locals_ = locals()
			for var in ['snapshot', 'file_path']:
				if var in _locals_: del _locals_[var]
			del _locals_

	del queue, symbol_upper