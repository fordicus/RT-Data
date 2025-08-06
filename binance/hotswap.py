# hotswap.py @2025-08-06 20:22:	DO NOT BLINDLY MODIFY THIS CODE

import asyncio, time, logging
from dataclasses import dataclass
from typing import Optional, Callable
from util import (
	my_name
)

#———————————————————————————————————————————————————————————————————————————————

@dataclass
class ConnectionState:
	task:			asyncio.Task
	is_active:		bool = False
	handoff_event:	Optional[asyncio.Event] = None
	creation_time:	float = 0.0

#———————————————————————————————————————————————————————————————————————————————

class HotSwapManager:

	#———————————————————————————————————————————————————————————————————————————
	
	def __init__(self):

		self.current_connection: Optional[ConnectionState] = None
		self.pending_connection: Optional[ConnectionState] = None
		self.swap_lock =		 asyncio.Lock()
		self.shutdown_event:	 Optional[asyncio.Event] = None
		self.hot_swap_tasks:	 list[asyncio.Task] = []

	#———————————————————————————————————————————————————————————————————————————

	def set_shutdown_event(self,
		shutdown_event: asyncio.Event
	):
		self.shutdown_event = shutdown_event

	#———————————————————————————————————————————————————————————————————————————

	def is_shutting_down(self
	) -> bool:
		
		return (
			self.shutdown_event
			and self.shutdown_event.is_set()
		)

	#———————————————————————————————————————————————————————————————————————————

	def _cleanup_completed_tasks(self):

		self.hot_swap_tasks = [
			task for task in self.hot_swap_tasks 
			if not task.done()
		]

	#———————————————————————————————————————————————————————————————————————————

	def is_ready_for_handoff(
		self
	) -> bool:

		return (self.pending_connection is not None and 
				not self.pending_connection.task.done())

	#———————————————————————————————————————————————————————————————————————————

	async def graceful_shutdown(self, logger):

		try:

			async with self.swap_lock:

				logger.info(
					f"[{my_name()}] shutting down HotSwapManager..."
				)

				if self.hot_swap_tasks:

					logger.info(
						f"[{my_name()}] force cancelling "
						f"{len(self.hot_swap_tasks)} hotswap tasks..."
					)
					
					for i, task in enumerate(self.hot_swap_tasks):

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

						if self.hot_swap_tasks:
							done, pending = await asyncio.wait_for(
								asyncio.wait(
									self.hot_swap_tasks,
									return_when=asyncio.ALL_COMPLETED
								),
								timeout=1.0,
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
							f"[{my_name()}] hotswap tasks cleanup timed out: "
							f"forcing cleanup"
						)

					except Exception as e:

						if not isinstance(e, asyncio.CancelledError):
							logger.warning(
								f"[{my_name()}] "
								f"hotswap tasks cleanup error: {e}"
							)
					
					self.hot_swap_tasks.clear()

				if self.pending_connection:

					try:

						if not self.pending_connection.task.done():

							self.pending_connection.task.cancel()

							try:

								await asyncio.wait_for(
									self.pending_connection.task,
									timeout=0.2
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

	async def initiate_hot_swap(self,
		task_factory, logger
	):

		if self.is_shutting_down():

			logger.info(
				f"[{my_name()}] "
				f"Hotswap cancelled - shutdown in progress"
			)

			return

		async with self.swap_lock:

			if self.pending_connection:

				return
				
			logger.info(f"[{my_name()}]🔌 new conn. starts")
			
			handoff_event = asyncio.Event()
			new_task = asyncio.create_task(
				task_factory(handoff_event, True)
			)
			
			self._cleanup_completed_tasks()
			self.hot_swap_tasks.append(new_task)
			
			self.pending_connection = ConnectionState(
				task=new_task,
				is_active=False,
				handoff_event=handoff_event,
				creation_time=time.time()
			)

	#———————————————————————————————————————————————————————————————————————————

	async def _cleanup_old_connection(self,
		old_conn: ConnectionState, logger
	):

		try:

			await asyncio.sleep(1.0)
			
			if not old_conn.task.done():

				old_conn.task.cancel()

				try: await old_conn.task
				except asyncio.CancelledError: pass
					
			logger.info(
				f"[{my_name()}]🧹 old conn. closed"
			)
			
		except Exception as e:

			logger.warning(
				f"[{my_name()}] cleanup error: {e}"
			)

	#———————————————————————————————————————————————————————————————————————————

	async def complete_handoff(self, logger):

		async with self.swap_lock:
			if not self.pending_connection:
				return
				
			logger.info(f"[{my_name()}]🤝 handoff")
			
			self.pending_connection.is_active = True
			self.pending_connection.handoff_event.set()
			
			if self.current_connection:
				self.current_connection.is_active = False
			
			old_connection = self.current_connection
			self.current_connection = self.pending_connection
			self.pending_connection = None
			
			if old_connection:
				asyncio.create_task(
					self._cleanup_old_connection(
						old_connection, logger
					)
				)

#———————————————————————————————————————————————————————————————————————————————

async def schedule_backup_creation(
	hot_swap_manager:		 HotSwapManager,
	backup_start_time:		 float,
	task_factory:			 Callable[[asyncio.Event, bool], asyncio.Task],
	logger:					 logging.Logger,
	back_up_ready_ahead_sec: float,
	connection_start_time:	 float,
	check_interval:			 float = 1.0
):
	try:
		
		while True:

			if hot_swap_manager.is_shutting_down():

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
				
				await hot_swap_manager.initiate_hot_swap(
					task_factory, logger
				)
				break
				
			await asyncio.sleep(check_interval)

	except asyncio.CancelledError:
		
		pass # logging unnecessary
		
	except Exception as e:
		
		logger.error(
			f"[{my_name()}] {e}",
			exc_info=True,
		)

#———————————————————————————————————————————————————————————————————————————————