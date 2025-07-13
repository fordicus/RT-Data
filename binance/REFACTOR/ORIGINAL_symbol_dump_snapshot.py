async def symbol_dump_snapshot(symbol: str) -> None:

	"""
	Writes snapshots to disk and
	triggers daily merge for the given symbol.
	"""

	global SYMBOL_TO_FILE_HANDLES, SNAPSHOTS_QUEUE_DICT
	global LATEST_JSON_FLUSH, JSON_FLUSH_INTERVAL
	global EVENT_STREAM_ENABLE

	queue = SNAPSHOTS_QUEUE_DICT[symbol]

	while True:

		# Block until new snapshot is received

		try:

			snapshot = await queue.get()

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"Failed to get snapshot from queue: {e}",
				exc_info=True
			)

			continue

		if not EVENT_STREAM_ENABLE.is_set():

			break

		# ── Compute suffix (time block) and day string (UTC)

		try:

			event_ts_ms = snapshot.get("eventTime", get_current_time_ms())
			suffix		= get_file_suffix(SAVE_INTERVAL_MIN, event_ts_ms)
			day_str		= get_date_from_suffix(suffix)

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"Failed to compute suffix/day: {e}",
				exc_info=True
			)

			continue

		# ── Build filename and full path

		try:

			filename = f"{symbol.upper()}_orderbook_{suffix}.jsonl"
			tmp_dir = os.path.join(
				LOB_DIR,
				"temporary",
				f"{symbol.upper()}_orderbook_{day_str}",
			)
			os.makedirs(tmp_dir, exist_ok=True)
			file_path = os.path.join(tmp_dir, filename)

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"Failed to build file path: {e}",
				exc_info=True
			)

			continue

		# ── Retrieve last writer (if any)

		last_suffix, writer = SYMBOL_TO_FILE_HANDLES.get(symbol, (None, None))

		# ────────────────────────────────────────────────────────────────────
		# 🔧 STEP 1: Handle file rotation and compression FIRST
		# This ensures all previous files are zipped before merge check
		# ────────────────────────────────────────────────────────────────────

		if last_suffix != suffix:

			if writer:

				try:

					writer.close()

				except Exception as e:

					logger.error(
						f"[symbol_dump_snapshot][{symbol.upper()}] "
						f"Close failed → {e}",
						exc_info=True
					)

				# 🔧 Compress previous file immediately after closing
				try:

					last_day_str = get_date_from_suffix(last_suffix)
					last_tmp_dir = os.path.join(
						LOB_DIR,
						"temporary",
						f"{symbol.upper()}_orderbook_{last_day_str}",
					)
					last_file_path = os.path.join(
						last_tmp_dir,
						f"{symbol.upper()}_orderbook_{last_suffix}.jsonl"
					)

					if os.path.exists(last_file_path):

						zip_and_remove(last_file_path)

					else:

						logger.error(
							f"[symbol_dump_snapshot][{symbol.upper()}] "
							f"File not found for compression: {last_file_path}"
						)

				except Exception as e:

					logger.error(
						f"[symbol_dump_snapshot][{symbol.upper()}] "
						f"zip_and_remove(last_file_path={last_file_path}) "
						f"failed for last_suffix={last_suffix}: {e}",
						exc_info=True
					)

			# 🔧 Open new file writer for current suffix
			try:

				writer = open(file_path, "a", encoding="utf-8")

			except OSError as e:

				logger.error(
					f"[symbol_dump_snapshot][{symbol.upper()}] "
					f"Open failed: {file_path} → {e}",
					exc_info=True
				)

				continue  # Skip this snapshot

			SYMBOL_TO_FILE_HANDLES[symbol] = (suffix, writer)

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
							f"[symbol_dump_snapshot][{symbol.upper()}] "
							f"Triggered merge for {last_day} "
							f"(current day: {day_str})."
						)

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"Failed to check/trigger merge: {e}",
				exc_info=True
			)

		# ────────────────────────────────────────────────────────────────────
		# Write snapshot as compact JSON line
		# ────────────────────────────────────────────────────────────────────

		try:

			line = json.dumps(snapshot, separators=(",", ":"))
			writer.write(line + "\n")
			writer.flush()

			# Update flush monitoring
			
			current_time = get_current_time_ms()

			JSON_FLUSH_INTERVAL[symbol] = (
				current_time - LATEST_JSON_FLUSH[symbol]
			)
			
			LATEST_JSON_FLUSH[symbol] = current_time

		except Exception as e:

			logger.error(
				f"[symbol_dump_snapshot][{symbol.upper()}] "
				f"Write failed: {file_path} → {e}",
				exc_info=True
			)

			# Invalidate writer for next iteration

			SYMBOL_TO_FILE_HANDLES.pop(symbol, None)

			continue