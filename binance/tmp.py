				#———————————————————————————————————————————————————————————————
				# any backup
				# → wait_for(handoff_event.wait(), timeout)
				# 	→ main
				# 	→ prepare the next backup
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
						# prepare the next backup
						#———————————————————————————————————————————————————————

						create_task_with_creation_time(
							hotswap_manager, schedule_backup_creation(
								#———————————————————————————————————————————————
								hotswap_manager,
								backup_start_time,
								#———————————————————————————————————————————————
								lambda _event, _is_backup: wrapped_put_snapshot(
									#———————————————————————————————————————————
									websocket_recv_interval,
									websocket_recv_intv_stat,
									put_snapshot_interval,
									#———————————————————————————————————————————
									snapshots_queue_dict,
									#———————————————————————————————————————————
									event_stream_enable,
									mean_latency_dict,
									event_1st_snapshot,
									#———————————————————————————————————————————
									max_backoff,
									base_backoff,
									reset_cycle_after,
									reset_backoff_level,
									#———————————————————————————————————————————
									ws_url,
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
							)
						)

						hotswap_manager.handoff_completed = False
						
						logger.info(
							f"[{my_name()}]📅 next backup scheduled"
						)

					#———————————————————————————————————————————————————————————
					# unutilized backup returns
					#———————————————————————————————————————————————————————————

					except asyncio.TimeoutError:

						logger.critical(
							f"[{my_name()}] backup handoff timeout, "
							f"terminating backup"
						)
						return

					#———————————————————————————————————————————————————————————
					# backup returns whenever there's an exception
					#———————————————————————————————————————————————————————————

					except Exception as e:

						logger.critical(
							f"[{my_name()}] backup connection error: {e}"
						)
						return