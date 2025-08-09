				#———————————————————————————————————————————————————————————————
				# initial main: prepare a backup
				#———————————————————————————————————————————————————————————————

				elif (
					not is_backup
					and not hotswap_prepared
				):

					hotswap_prepared = True

					create_task_with_creation_time(
						hotswap_manager, schedule_backup_creation(
							#———————————————————————————————————————————————————
							hotswap_manager,
							backup_start_time,
							#———————————————————————————————————————————————————
							lambda _event, _is_backup: wrapped_put_snapshot(
								#———————————————————————————————————————————————
								websocket_recv_interval,
								websocket_recv_intv_stat,
								put_snapshot_interval,
								#———————————————————————————————————————————————
								snapshots_queue_dict,
								#———————————————————————————————————————————————
								event_stream_enable,
								mean_latency_dict,
								event_1st_snapshot,
								#———————————————————————————————————————————————
								max_backoff,
								base_backoff,
								reset_cycle_after,
								reset_backoff_level,
								#———————————————————————————————————————————————
								ws_url,
								wildcard_stream_binance_com_port,
								ports_stream_binance_com,
								ws_ping_interval,
								ws_ping_timeout,
								#———————————————————————————————————————————————
								symbols,
								logger,
								#———————————————————————————————————————————————
								port_cycling_period_hrs,
								back_up_ready_ahead_sec,
								hotswap_manager,
								shutdown_event,
								_event,
								_is_backup,
								#———————————————————————————————————————————————
							),
							#———————————————————————————————————————————————————
							logger,
							back_up_ready_ahead_sec,
							ws_start_time,
							#———————————————————————————————————————————————————
						)
					)

					logger.info(
						f"[{my_name()}]📅 initial backup scheduled"
					)