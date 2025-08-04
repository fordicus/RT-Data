# latency.py

#———————————————————————————————————————————————————————————————————————————————
# Binance latency sanity check
#———————————————————————————————————————————————————————————————————————————————
# Observed ≈135 ms one‑way latency (local_recv_ts − server_event_ts) from Swiss.
#
# Plausibility:
#   • Likely route: Switzerland → AWS ap‑northeast‑1 (Tokyo, Spot REST primary)
#	 or Cloudflare / GCP PoP → Binance WS broker.
#	 Propagation CH→JP ≈50‑60 ms; add router, TLS, Anycast & broker hops
#	 ≈10‑25 ms ⇒ practical upper‑bound 100‑140 ms → 135 ms fits.
#   • Binance exposes several hosts:
#	   - Primary REST:   api.binance.com  (Tokyo)
#	   - Alternatives:   api1.binance.com, api‑gcp.binance.com
#	   - Market data:	data‑api.binance.vision
#	 All WS endpoints are Anycast, so region may vary per connection.
#   • Measurement: server_event_ts comes in the WS payload; Chrony‑synced local
#	 clock, parsing+GC <1 ms, clock skew ±1 ms ⇒ figure is trustworthy.
#———————————————————————————————————————————————————————————————————————————————

import asyncio, logging
import websockets, time, random, statistics, orjson
import numpy as np
from collections import deque
from typing import Optional
from util import (
	my_name,
	NanoTimer,
	get_current_time_ms,
	geo, format_ws_url,
	ensure_logging_on_exception,
)

#———————————————————————————————————————————————————————————————————————————————

async def gate_streaming_by_latency(
	event_latency_valid:  asyncio.Event,
	event_stream_enable:  asyncio.Event,
	mean_latency_dict:	  dict[str, int],
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
				mean_latency_dict[s]
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

@ensure_logging_on_exception
async def estimate_latency(
	websocket_peer:			dict[str, str],
	ws_ping_interval:		Optional[int],
	ws_ping_timeout:		Optional[int],
	latency_deque_size:		int,
	latency_sample_min:		int,
	mean_latency_dict:		dict[str, int],
	latency_threshold_ms:	int,
	event_latency_valid:  	asyncio.Event,
	base_backoff:			int,
	max_backoff:			int,
	reset_cycle_after:		int,
	reset_backoff_level:	int,
	symbols:				list[str],
	logger:					logging.Logger,
	base_interval_ms:		int   = 100,
	ws_timeout_multiplier:	float =	  8.0,
	ws_timeout_default_sec:	float =	  2.0,
	ws_timeout_min_sec:		float =	  1.0,
):

	"""—————————————————————————————————————————————————————————————————————————
	CORE FUNCTIONALITY:
		Measure network latency via @depth@100ms stream with timeout-based recv
	—————————————————————————————————————————————————————————————————————————"""

	def update_ws_recv_timeout(
		data:		deque[float],
		stat:		dict[str, float],
		multiplier: float,
		default:	float,
		minimum:	float,
	) -> float:		# ws_timeout_sec

		if len(data) >= max(data.maxlen, 300):
			
			stat['p90'] = np.percentile(list(data), 90)
			return max(stat['p90'] * multiplier, minimum)

		else:

			return max(default, minimum)

	#———————————————————————————————————————————————————————————————————————————

	async def calculate_backoff_and_sleep(
		retry_count: int,
		symbol: str = "UNKNOWN",
		last_success_time: Optional[float] = None,
		reset_retry_count_after_sec: float = 3600,	# an hour
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
				f"[{my_name()}][{symbol.upper()}] "
				f"Resetting retry_count after {reset_retry_count_after_sec} sec; "
				f"previous retry_count={retry_count}."
			)

			retry_count = 0

		backoff = min(
			max_backoff,
			base_backoff ** retry_count
		) + random.uniform(0, 1)

		logger.warning(
			f"[{my_name()}][{symbol.upper()}] "
			f"Retrying in {backoff:.1f} seconds..."
		)
		
		await asyncio.sleep(backoff)
		
		return retry_count, last_success_time

	#———————————————————————————————————————————————————————————————————————————

	url = (
		"wss://stream.binance.com:9443/stream?streams="
		+ "/".join(f"{symbol}@depth@100ms" for symbol in symbols)
	)

	ws_retry_cnt = 0
	last_success_time = time.time()

	ws_timeout_sec = ws_timeout_default_sec
	last_recv_time_ns = None

	websocket_recv_interval	 = deque(maxlen=max(len(symbols), 300))
	websocket_recv_intv_stat = {"p90": float('inf')}

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

	#———————————————————————————————————————————————————————————————————————————

	while True:

		cur_symbol = "UNKNOWN"

		try:

			async with websockets.connect(
				url,
				ping_interval = ws_ping_interval,
				ping_timeout  = ws_ping_timeout
			) as ws:

				ip, port = ws.remote_address or ("?", "?")

				try:

					loc = await geo(ip) if ip != "?" else "?"

				except RuntimeError as e:

					if "cannot reuse already awaited coroutine" in str(e):

						loc = "UNKNOWN"
						logger.warning(
							f"[{my_name()}] Coroutine reuse error, "
							f"using fallback location"
						)

					else:

						raise

				except Exception as e:

					loc = "UNKNOWN"
					logger.warning(
						f"[{my_name()}] Failed to get location for {ip}: {e}"
					)

				websocket_peer["value"] = (
					f"{ip}:{port}  ({loc})"
				)

				logger.info(
					f"[{my_name()}] WebSocket Peer {websocket_peer['value']}"
				)
				
				logger.info(
					f"[{my_name()}] "
					f"Connected to:\n"
					f"{format_ws_url(url, '(@depth)')}\n"
				)

				ws_retry_cnt = 0
				last_success_time = time.time()

				while True:

					try:

						raw_msg = await asyncio.wait_for(
							ws.recv(),
							timeout = ws_timeout_sec
						)

						try:

							#———————————————————————————————————————————————————————
							# LATENCY MEASUREMENT ACCURACY & SYSTEM REQUIREMENTS
							#———————————————————————————————————————————————————————
							# From
							# 	`message = orjson.loads(raw_msg)`
							# to
							#	mean_latency_dict[symbol] = int(
							#		statistics.fmean(
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

								mean_latency_dict[symbol] = int(
									statistics.fmean(
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
											mean_latency_dict[s]
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

							#———————————————————————————————————————————————————————
							# Statistics on Websocket Receipt Interval (put_snapshot과 동일)
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

							logger.warning(
								f"[{my_name()}] "
								f"Failed to process message: {e}",
								exc_info=True
							)
							continue

					except asyncio.TimeoutError:

						ws_retry_cnt += 1
						
						logger.warning(
							f"[{my_name()}]\n"
							f"\tNo latency data received for {ws_timeout_sec:.6f} seconds.\n"
							f"\tp90 ws.recv() intv.: {websocket_recv_intv_stat['p90']:.6f}.\n"
							f"\tReconnecting..."
						)

						ws_retry_cnt, last_success_time = await calculate_backoff_and_sleep(
							ws_retry_cnt, cur_symbol, last_success_time,
						)

						break

		except asyncio.CancelledError:
			# propagate so caller can shut down gracefully
			raise

		except Exception as e:

			ws_retry_cnt += 1

			logger.warning(
				f"[{my_name()}] "
				f"WebSocket connection error "
				f"(attempt {ws_retry_cnt}): {e}",
				exc_info=True
			)

			event_latency_valid.clear()

			for symbol in symbols:

				latency_dict[symbol].clear()
				depth_update_id_dict[symbol] = 0

			ws_retry_cnt, last_success_time = await calculate_backoff_and_sleep(
				ws_retry_cnt, cur_symbol, last_success_time,
			)

		finally:

			logger.info(
				f"[{my_name()}] "
				f"WebSocket connection closed."
			)

#———————————————————————————————————————————————————————————————————————————————