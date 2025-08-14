except asyncio.TimeoutError as e:

	if hotswap_manager.is_shutting_down(): break

	ws_retry_cnt += 1

	quantile_ms = websocket_recv_intv_stat['p90'] * 1000.

	reason = (
		f"no data received for "
		f"{ws_timeout_sec:.2f}s; "
		f"p90 recv intv "
		f"{quantile_ms:.2f}ms"
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
