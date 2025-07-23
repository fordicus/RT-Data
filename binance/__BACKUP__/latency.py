# latency.py

#———————————————————————————————————————————————————————————————————————————————

import asyncio, logging
import websockets, orjson
import statistics, random
from collections import deque
from typing import Optional
from util import (
	my_name,
	NanoTimer,
	get_current_time_ms,
	format_ws_url,
)

#———————————————————————————————————————————————————————————————————————————————

async def gate_streaming_by_latency(
	event_latency_valid:  asyncio.Event,
	event_stream_enable:  asyncio.Event,
	median_latency_dict:  dict[str, int],
	latency_signal_sleep: float,
	symbols:			  list[str],
	logger:				  logging.Logger,
):

	has_logged_warmup = False

	while True:

		try:

			latency_passed = event_latency_valid.is_set()
			stream_currently_on = event_stream_enable.is_set()
			has_all_latency = all(
				median_latency_dict[s]
				is not None
				for s in symbols
			)

			if (
				latency_passed
				and not stream_currently_on
			):

				logger.info(
					f"[{my_name()}] "
					f"Latency normalized. "
					f"Enable LOB stream.\n"
				)

				event_stream_enable.set()
				has_logged_warmup = False

			elif not latency_passed:

				if (
					not has_all_latency
					and not has_logged_warmup
				):

					logger.info(
						f"[{my_name()}] "
						f"Warming up latency "
						f"measurements...\n"
					)

					has_logged_warmup = True

				elif (
					has_all_latency
					and stream_currently_on
				):

					logger.warning(
						f"[{my_name()}] "
						f"Latency degraded. "
						f"Pausing LOB stream."
					)

					event_stream_enable.clear()

			await asyncio.sleep(latency_signal_sleep)

		except Exception as e:

			logger.error(
				f"[{my_name()}] "
				f"Exception in latency gate: "
				f"{e}",
				exc_info=True
			)

			await asyncio.sleep(latency_signal_sleep)

#———————————————————————————————————————————————————————————————————————————————

async def estimate_latency(
	ws_ping_interval:		Optional[int],
	ws_ping_timeout:		Optional[int],
	latency_deque_size:		int,
	latency_sample_min:		int,
	median_latency_dict:	dict[str, int],			# shared
	latency_threshold_ms:	int,
	event_latency_valid:  	asyncio.Event,			# shared
	base_backoff:			int,
	max_backoff:			int,
	reset_cycle_after:		int,
	reset_backoff_level:	int,
	symbols:				list[str],
	logger:					logging.Logger,
):

	url = (
		"wss://stream.binance.com:9443/stream?streams="
		+ "/".join(f"{symbol}@depth" for symbol in symbols)
	)

	reconnect_attempt = 0

	depth_update_id_dict: dict[str, int] = {}
	depth_update_id_dict.clear()
	depth_update_id_dict.update({
		symbol: 0
		for symbol in symbols
	})

	latency_dict: dict[str, deque[int]] = {}
	latency_dict.clear()
	latency_dict.update({
		symbol: deque(maxlen=latency_deque_size)
		for symbol in symbols
	})

	while True:

		try:

			async with websockets.connect(
				url,
				ping_interval = ws_ping_interval,
				ping_timeout  = ws_ping_timeout
			) as ws:

				logger.info(
					f"[{my_name()}] "
					f"Connected to:\n"
					f"{format_ws_url(url, '(@depth)')}\n"
				)

				reconnect_attempt = 0

				async for raw_msg in ws:

					try:

						#———————————————————————————————————————————————————————
						# LATENCY MEASUREMENT ACCURACY & SYSTEM REQUIREMENTS
						#———————————————————————————————————————————————————————
						# From
						# 	`message = orjson.loads(raw_msg)`
						# to
						#	median_latency_dict[symbol] = int(
						#		statistics.median(
						#			latency_dict[symbol]
						#		)
						#	),
						# execution time is sub-millisec. even on basic Python
						# interpreter without optimization. This ensures
						# accurate network latency measurement with negligible
						# computational delay.
						#———————————————————————————————————————————————————————
						# Time Synchronization: Client system uses Chrony with
						# trusted local time servers. Since latency measurement
						# relies on `get_current_time_ms(): time.time_ns()`,
						# accurate system clock synchronization is essential.
						#———————————————————————————————————————————————————————

						message = orjson.loads(raw_msg)
						data = message.get("data", {})
						server_time_ms = data.get("E")

						if server_time_ms is None:
							continue  # drop malformed

						stream_name = message.get("stream", "")
						symbol = stream_name.split(
							"@", 1
						)[0].lower()

						if symbol not in symbols:
							continue  # ignore unexpected

						update_id = data.get("u")

						if ((update_id is None) or
							(update_id <= 
							 depth_update_id_dict.get(symbol, 0))
						): continue  # duplicate or out-of-order

						#———————————————————————————————————————————————————————

						depth_update_id_dict[symbol] = update_id

						latency_ms = (
							get_current_time_ms() - server_time_ms
						)

						latency_dict[symbol].append(latency_ms)

						if (
							len(latency_dict[symbol])
							>= latency_sample_min
						):

							median_latency_dict[symbol] = int(
								statistics.median(
									latency_dict[symbol]
								)
							)

							#———————————————————————————————————————————————————

							if all(
								(	
									(
										len(latency_dict[s])
										>= latency_sample_min
									)
									and (
										statistics.median(
											latency_dict[s]
										)
										< latency_threshold_ms
									)
								)	for s in symbols
							):

								if not event_latency_valid.is_set():

									event_latency_valid.set()

									logger.info(
										f"[{my_name()}] "
										f"Latency OK — "
										f"All symbols within "
										f"threshold. Event set."
									)
							
							else:

								event_latency_valid.clear()

							#———————————————————————————————————————————————————

					except Exception as e:

						logger.warning(
							f"[{my_name()}] "
							f"Failed to process message: {e}",
							exc_info=True
						)
						continue

		except Exception as e:

			reconnect_attempt += 1

			logger.warning(
				f"[{my_name()}] "
				f"WebSocket connection error "
				f"(attempt {reconnect_attempt}): {e}",
				exc_info=True
			)

			event_latency_valid.clear()

			for symbol in symbols:

				latency_dict[symbol].clear()
				depth_update_id_dict[symbol] = 0

			backoff_sec = (
				min(
					max_backoff,
					base_backoff * (2 ** reconnect_attempt)
				)
				+ random.uniform(0, 1)
			)

			if reconnect_attempt > reset_cycle_after:

				reconnect_attempt = reset_backoff_level

			logger.warning(
				f"[{my_name()}] "
				f"Retrying in {backoff_sec:.1f} seconds "
				f"(attempt {reconnect_attempt})..."
			)

			await asyncio.sleep(backoff_sec)

		finally:

			logger.info(
				f"[{my_name()}] "
				f"WebSocket connection closed."
			)

#———————————————————————————————————————————————————————————————————————————————