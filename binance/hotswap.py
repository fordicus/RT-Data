# hotswap.py @2025-08-11 11:43Z / DO NOT BLINDLY MODIFY THIS CODE

#———————————————————————————————————————————————————————————————————————————————
# Designed for asyncio.Task: event-driven, task-agnostic hot-swapping with
# seamless, non-blocking transitions and robust lifecycle management.
#———————————————————————————————————————————————————————————————————————————————

import asyncio, time, logging
from dataclasses import dataclass
from typing import Callable, Awaitable, Any, Optional
from util import (
	my_name
)

#———————————————————————————————————————————————————————————————————————————————

@dataclass
class ConnectionState:
	
	task:		   asyncio.Task
	is_active:	   bool = False
	handoff_event: Optional[asyncio.Event] = None
	creation_time: float = 0.0

#———————————————————————————————————————————————————————————————————————————————

class HotSwapManager:

	#———————————————————————————————————————————————————————————————————————————
	
	def __init__(self, 
		name:			str,
		shutdown_event:	asyncio.Event,
	):

		self.name =					name
		self.current_port_index =	-1
		self.current_connection:	Optional[ConnectionState] = None
		self.pending_connection:	Optional[ConnectionState] = None
		self.swap_lock =			asyncio.Lock()
		self.shutdown_event:		asyncio.Event = shutdown_event
		self.hotswap_tasks:			list[asyncio.Task] = []
		self.handoff_completed =	False

	#———————————————————————————————————————————————————————————————————————————

	def is_shutting_down(self
	) -> bool:
		
		return (
			self.shutdown_event
			and self.shutdown_event.is_set()
		)

	#———————————————————————————————————————————————————————————————————————————

	def append_task_w_creation_time(self,
		task: asyncio.Task,

	):
		task.creation_time = time.time()
		self.hotswap_tasks.append(task)

	#———————————————————————————————————————————————————————————————————————————

	def cycle_port_number(self,						# utilize various ws ports
		ports_list: list[str],
	) -> tuple[str, int]:
		
		#———————————————————————————————————————————————————————————————————————

		def get_next_port_index(
			ports_count: int,
		) -> int:

			self.current_port_index = (
				(self.current_port_index + 1) % ports_count
			)
			
			return self.current_port_index

		#———————————————————————————————————————————————————————————————————————

		new_index = (
			get_next_port_index(len(ports_list))
		)

		return ports_list[new_index], new_index

	#———————————————————————————————————————————————————————————————————————————

	def is_ready_for_handoff(
		self
	) -> bool:

		return (
			self.pending_connection is not None
			and not self.pending_connection.task.done()
			)

	#———————————————————————————————————————————————————————————————————————————

	async def graceful_shutdown(self, 
		logger: logging.Logger,
	):

		try:

			async with self.swap_lock:

				logger.info(
					f"[{my_name()}] shutting down HotSwapManager..."
				)

				if self.hotswap_tasks:

					logger.info(
						f"[{my_name()}] cancelling "
						f"{len(self.hotswap_tasks)} "
						f"hotswap tasks..."
					)
					
					for i, task in enumerate(self.hotswap_tasks):

						if not task.done():

							task.cancel()

							logger.info(
								f"[{my_name()}] "
								f"hotswap task-{i+1} cancelled"
							)

					#———————————————————————————————————————————————————————————
					# DO NOT BLINDLY MODIFY THE TRY-EXCEPT BLOCK BELOW
					#———————————————————————————————————————————————————————————

					try:

						#———————————————————————————————————————————————————————
						# asyncio.wait() instead of asyncio.gather() to avoid 
						# "never retrieved" error
						#———————————————————————————————————————————————————————

						if self.hotswap_tasks:

							done, pending = await asyncio.wait_for(
								asyncio.wait(
									self.hotswap_tasks,
									return_when=asyncio.ALL_COMPLETED
								),
								timeout = 1.0,
							)
							
							# Silently handle any exceptions in the completed

							for task in done:

								try:	# This retrieves any exception

									task.result()

								except asyncio.CancelledError:

									pass  # Expected during shutdown

								except Exception:

									# Other exceptions also silently

									pass

					#———————————————————————————————————————————————————————————

					except asyncio.TimeoutError:

						logger.warning(
							f"[{my_name()}] hotswap tasks "
							f"cleanup timed out: "
							f"forcing cleanup"
						)

					except Exception as e:

						if not isinstance(e, asyncio.CancelledError):
							logger.warning(
								f"[{my_name()}] "
								f"hotswap tasks cleanup error: {e}"
							)
					
					self.hotswap_tasks.clear()

				if self.pending_connection:

					try:

						if not self.pending_connection.task.done():

							self.pending_connection.task.cancel()

							try:

								await asyncio.wait_for(
									self.pending_connection.task,
									timeout = 0.2
								)

							except (
								asyncio.CancelledError,
								asyncio.TimeoutError,
							):

								pass

					except Exception as e:

						logger.warning(
							f"failed to cleanup pending connection: {e}"
						)

				self.current_connection = None
				self.pending_connection = None
				
				logger.info(
					f"[{my_name()}] HotSwapManager shutdown complete"
				)

		except asyncio.CancelledError:
			
			raise # logging unnecessary

		except Exception as e:

			logger.error(
				f"[{my_name()}] error during hotswapmanager shutdown: {e}"
			)

	#———————————————————————————————————————————————————————————————————————————

	async def prepare_hotswap(self,
		task_factory: Callable[[asyncio.Event, bool], asyncio.Task],
		logger:		  logging.Logger,
	):

		#———————————————————————————————————————————————————————————————————————

		def cleanup_completed_tasks():

			self.hotswap_tasks = [
				task
				for task in self.hotswap_tasks 
				if not task.done()
			]

		#———————————————————————————————————————————————————————————————————————

		if self.is_shutting_down():

			logger.info(
				f"[{my_name()}] "
				f"Hotswap cancelled - shutdown in progress"
			)

			return

		async with self.swap_lock:

			if self.pending_connection:

				return
				
			handoff_event = asyncio.Event()

			creation_timestamp = time.time()
			new_task = asyncio.create_task(
				task_factory(
					handoff_event, 
					True,				# is_backup
				)
			)
			logger.info(f"[{my_name()}]🔗 backup conn. prepared")
			new_task.creation_time = creation_timestamp
			
			cleanup_completed_tasks()						# critical
			self.hotswap_tasks.append(new_task)
			
			self.pending_connection = ConnectionState(
				task		  = new_task,
				is_active	  = False,
				handoff_event = handoff_event,
				creation_time = creation_timestamp,
			)

	#———————————————————————————————————————————————————————————————————————————

	async def commit_hotswap(self,
		logger: logging.Logger,
	):

		async with self.swap_lock:

			if not self.pending_connection:

				return
				
			logger.info(f"[{my_name()}]🤝 handoff")
			
			self.pending_connection.is_active = True
			self.pending_connection.handoff_event.set()
			
			if self.current_connection:

				self.current_connection.is_active = False
			
			self.current_connection = self.pending_connection
			self.pending_connection = None
			self.handoff_completed  = True

#———————————————————————————————————————————————————————————————————————————————

async def hsm_schedule_backup(
	#———————————————————————————————————————————————————————————————————————————
	hotswap_manager:		 HotSwapManager,
	backup_start_time:		 float,
	#———————————————————————————————————————————————————————————————————————————
	task_factory:			 Callable[[asyncio.Event, bool], asyncio.Task],
	#———————————————————————————————————————————————————————————————————————————
	logger:					 logging.Logger,
	back_up_ready_ahead_sec: float,
	connection_start_time:	 float,
	check_interval:			 float = 0.1,
	#———————————————————————————————————————————————————————————————————————————
):

	try:
		
		while True:

			if hotswap_manager.is_shutting_down():

				logger.info(
					f"[{my_name()}] backup creation cancelled "
					f"- shutdown in progress"
				)
				return
				
			connection_age = time.time() - connection_start_time
			
			if connection_age >= backup_start_time:
				
				logger.info(
					f"[{my_name()}]🔜 backup scheduled / "
					f"T-{back_up_ready_ahead_sec:.2f}s / "
					f"age {connection_age:.2f}s"
				)
				
				await hotswap_manager.prepare_hotswap(
					task_factory, logger,
				)
				break
				
			await asyncio.sleep(check_interval)

	except asyncio.CancelledError:
		
		pass # logging unnecessary
		
	except Exception as e:
		
		logger.error(
			f"[{my_name()}] {e}",
			exc_info = True,
		)

#———————————————————————————————————————————————————————————————————————————————

def hsm_create_task(
	hotswap_manager: HotSwapManager,
	coro: Awaitable[Any],				# hsm_schedule_backup
	name: Optional[str] = None,
):

	hotswap_manager.append_task_w_creation_time(
		asyncio.create_task(
			coro, name = name
		)
	)

#———————————————————————————————————————————————————————————————————————————————