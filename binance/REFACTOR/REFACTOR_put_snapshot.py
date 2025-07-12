async def put_snapshot() -> None:

	""" ————————————————————————————————————————————————————————————————
	CORE FUNCTIONALITY:
		await SNAPSHOTS_QUEUE_DICT[symbol].put(snapshot)
	————————————————————————————————————————————————————————————————————
	HINT:
		asyncio.Queue(maxsize=SNAPSHOTS_QUEUE_MAX)
	————————————————————————————————————————————————————————————————————
	CREATION:
		if __name__ == "__main__":
			async def main():
				asyncio.create_task(put_snapshot())
	————————————————————————————————————————————————————————————————————
	GLOBAL VARIABLES:
		WRITE:
			SNAPSHOTS_QUEUE_DICT:		dict[str, asyncio.Queue]
			SYMBOL_SNAPSHOTS_TO_RENDER: dict[str, dict]
			EVENT_1ST_SNAPSHOT:			asyncio.Event
		READ:
			LATENCY_GATE:
				EVENT_STREAM_ENABLE:	asyncio.Event
				LATENCY_DICT:			Dict[str, Deque[int]]
				MEDIAN_LATENCY_DICT:	Dict[str, int]
			WEBSOCKETS:
				WS_URL, WS_PING_INTERVAL, WS_PING_TIMEOUT
				MAX_BACKOFF, BASE_BACKOFF,
				RESET_CYCLE_AFTER, RESET_BACKOFF_LEVEL
			LOGICAL:
				SYMBOLS
	———————————————————————————————————————————————————————————————— """

	ws_retry_cnt = 0

	while True:

		symbol = "UNKNOWN"

		await EVENT_STREAM_ENABLE.wait()

		try:

			async with websockets.connect(WS_URL,
				ping_interval = WS_PING_INTERVAL,
				ping_timeout  = WS_PING_TIMEOUT
			) as ws:

				logger.info(
					f"[put_snapshot] Connected to:\n"
					f"{format_ws_url(WS_URL, '(depth20@100ms)')}\n"
				)
				
				ws_retry_cnt = 0

				async for raw in ws:

					try:

						msg	   = json.loads(raw)
						stream = msg.get("stream", "")
						symbol = stream.split("@", 1)[0].lower()

						del stream

						if symbol not in SYMBOLS:
							continue

						if ((not EVENT_STREAM_ENABLE.is_set()) or
							(not LATENCY_DICT[symbol])):
							continue

						data = msg.get("data", {})

						del msg

						last_update = data.get("lastUpdateId")
						if last_update is None:
							del last_update
							continue

						bids = data.get("bids", [])
						asks = data.get("asks", [])

						del data

						# ──────────────────────────────────────────────────
						# Binance partial streams like `@depth20@100ms`
						# do NOT include the server-side event timestamp
						# ("E"). Thus, we must rely on local receipt time
						# corrected by estimated network latency.
						# ──────────────────────────────────────────────────

						snapshot = {
							"lastUpdateId": last_update,
							"eventTime": (get_current_time_ms() - max(
								0, MEDIAN_LATENCY_DICT.get(symbol, 0)
							)),
							"bids": [[float(p), float(q)] for p, q in bids],
							"asks": [[float(p), float(q)] for p, q in asks],
						}

						del last_update, bids, asks

						# ──────────────────────────────────────────────────
						# `.qsize()` is less than or equal to one almost
						# surely, meaning that `SNAPSHOTS_QUEUE_DICT` is
						# being quickly consumed via `.get()`.
						# ──────────────────────────────────────────────────
						
						await SNAPSHOTS_QUEUE_DICT[symbol].put(snapshot)

						if not EVENT_1ST_SNAPSHOT.is_set():
							EVENT_1ST_SNAPSHOT.set()

						# ──────────────────────────────────────────────────
						# Currently, `SYMBOL_SNAPSHOTS_TO_RENDER` is
						# referenced nowhere almost surely:
						# 	no potential of memory issue
						# ──────────────────────────────────────────────────

						SYMBOL_SNAPSHOTS_TO_RENDER[symbol] = snapshot

						del snapshot

					except Exception as e:

						if 'symbol' not in locals():
							symbol = "UNKNOWN"

						logger.warning(
							f"[put_snapshot][{symbol.upper()}] "
							f"Failed to process message: {e}",
							exc_info=True
						)

						del e
						continue	# flow control does not skip `finally``

					finally:

						del symbol

		except Exception as e:

			ws_retry_cnt += 1

			if 'symbol' not in locals():
				symbol = "UNKNOWN"

			logger.warning(
				f"[put_snapshot][{symbol.upper()}] "
				f"WebSocket error "
				f"(ws_retry_cnt {ws_retry_cnt}): {e}",
				exc_info=True
			)

			backoff = min(MAX_BACKOFF,
				BASE_BACKOFF * (2 ** ws_retry_cnt)
			) + random.uniform(0, 1)

			if ws_retry_cnt > RESET_CYCLE_AFTER:
				ws_retry_cnt = RESET_BACKOFF_LEVEL

			logger.warning(
				f"[put_snapshot][{symbol.upper()}] "
				f"Retrying in {backoff:.1f} seconds..."
			)

			await asyncio.sleep(backoff)

			del e, backoff

		finally:

			if 'symbol' not in locals():
				symbol = "UNKNOWN"

			logger.info(
				f"[put_snapshot][{symbol.upper()}] "
				f"WebSocket connection closed."
			)

			del ws, symbol	# explicitly being deleted
		
	del ws_retry_cnt