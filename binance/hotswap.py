# hotswap.py @2025-08-07 16:46 / DO NOT BLINDLY MODIFY THIS CODE

#———————————————————————————————————————————————————————————————————————————————
# Designed for asyncio.Task: event-driven, task-agnostic hot-swapping with
# seamless, non-blocking transitions and robust lifecycle management.
#———————————————————————————————————————————————————————————————————————————————
#
#	EXAMPLE:
#
#		async def generic_task(
#			#
#			logger:			logging.Logger,
#			shutdown_event:	asyncio.Event,
#			handoff_event:	Optional[asyncio.Event] = None,
#			is_backup:		bool = False,
#			#
#		):
#			
#			is_active = not is_backup
#		
#			while not shutdown_event.is_set():
#				
#				if is_backup and handoff_event:
#					
#					await handoff_event.wait()
#					
#					is_active = True
#		
#				if not is_active:
#					
#					continue
#		
#				try:
#					
#					logger.info("Performing task operation...")
#					await asyncio.sleep(1)
#					
#				except Exception as e:
#					
#					logger.error(f"Error during task operation: {e}")
#		
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
	
	def __init__(self, name: str):

		self.name =					name
		self.current_port_index =	0
		self.current_connection:	Optional[ConnectionState] = None
		self.pending_connection:	Optional[ConnectionState] = None
		self.swap_lock =			asyncio.Lock()
		self.shutdown_event:		Optional[asyncio.Event] = None
		self.hot_swap_tasks:		list[asyncio.Task] = []
		self.handoff_completed =	False

	#———————————————————————————————————————————————————————————————————————————

	def set_shutdown_event(self,
		shutdown_event: asyncio.Event,
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

	def get_next_port_index(self, ports_count: int) -> int:

		self.current_port_index = (
			(self.current_port_index + 1) % ports_count
		)
		
		return self.current_port_index

	#———————————————————————————————————————————————————————————————————————————

	def _cleanup_completed_tasks(self):

		self.hot_swap_tasks = [
			task
			for task in self.hot_swap_tasks 
			if not task.done()
		]

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

				if self.hot_swap_tasks:

					logger.info(
						f"[{my_name()}] cancelling "
						f"{len(self.hot_swap_tasks)} "
						f"hotswap tasks..."
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
					
					self.hot_swap_tasks.clear()

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

			creation_timestamp = time.time()
			new_task = asyncio.create_task(
				task_factory(handoff_event, True)
			)
			new_task.creation_time = creation_timestamp
			
			self._cleanup_completed_tasks()
			self.hot_swap_tasks.append(new_task)
			
			self.pending_connection = ConnectionState(
				task		  = new_task,
				is_active	  = False,
				handoff_event = handoff_event,
				creation_time = creation_timestamp,
			)

	#———————————————————————————————————————————————————————————————————————————

	async def _cleanup_old_connection( self,
		old_conn: ConnectionState,
		logger:   logging.Logger,
	):

		try:

			await asyncio.sleep(2.0)
			
			if not old_conn.task.done():
		
				old_conn.task.cancel()

				try: 

					await asyncio.wait_for(
						old_conn.task,
						timeout = 0.5,
					)

				except (
					asyncio.CancelledError,
					asyncio.TimeoutError
				): 

					pass

			if old_conn.task in self.hot_swap_tasks:

				self.hot_swap_tasks.remove(old_conn.task)

			logger.info(
				f"[{my_name()}]🧹 old conn. closed"
			)
			
		except Exception as e:

			if not isinstance(e, asyncio.CancelledError):

				logger.warning(
					f"[{my_name()}] cleanup error: {e}"
				)

	#———————————————————————————————————————————————————————————————————————————

	async def cleanup_stale_tasks(self,
		max_age_sec: float,
		logger: logging.Logger,
	):
		
		for i, task in enumerate(
			self.hot_swap_tasks[:]
		):

			try: 

				running_duration = (
					time.time() - task.creation_time
				)

				if (
					running_duration
					> max_age_sec
				):
				
					if not task.done():
						
						task.cancel()
					
					self.hot_swap_tasks.remove(task)

					logger.warning(
						f"[{my_name()}] "
						f"hot_swap_tasks.remove(task) → "
						f"len(hot_swap_tasks): {len(self.hot_swap_tasks)}",
						flush = True,
					)

			except Exception as e:

				logger.error(
					f"[{my_name()}] e",
					exc_info = True,
				)
				raise

	#———————————————————————————————————————————————————————————————————————————

	async def commence_hotswap(self,
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
			
			old_connection = self.current_connection
			self.current_connection = self.pending_connection
			self.pending_connection = None
			self.handoff_completed  = True
			
			if old_connection:

				asyncio.create_task(
					self._cleanup_old_connection(
						old_connection, logger
					)
				)

#———————————————————————————————————————————————————————————————————————————————

async def schedule_backup_creation(
	#———————————————————————————————————————————————————————————————————————————
	hot_swap_manager:		 HotSwapManager,
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
				
				await hot_swap_manager.prepare_hotswap(
					task_factory, logger
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

def create_task_with_creation_time(
	coro: Awaitable[Any],
	*,
	name: Optional[str] = None,
) -> asyncio.Task:

	task = asyncio.create_task(
		coro, name = name
	)
	task.creation_time = time.time()
	return task

#———————————————————————————————————————————————————————————————————————————————