# shutdown.py

r"""————————————————————————————————————————————————————————————————————————————
Graceful shutdown management for stream_binance.py

How to Use:
	1. Create shutdown manager:
		shutdown_manager = create_shutdown_manager(logger)

	2. Register resources:
		shutdown_manager.register_executors(merge=executor)

	3. Register signals:
		shutdown_manager.register_signal_handlers()

	4. For controlled termination:
		graceful_shutdown() 

Dependency:
	- logging: For shutdown operation logging
	- signal, sys: For signal handling and system exit
	- threading: For thread-safe shutdown state management
	- concurrent.futures: For ProcessPoolExecutor management

Functionality:
	- Centralized shutdown handling with proper resource cleanup
	- Thread-safe shutdown state management to prevent race conditions
	- Signal handler registration for graceful SIGINT/SIGTERM handling
	- Prevents duplicate shutdown attempts through internal state tracking

IO Structure:
	INPUT:  ProcessPoolExecutors, file handles, symbols list, callbacks
	OUTPUT: Clean shutdown with proper resource cleanup and logging
—————————————————————————————————————————————————————————————————————————————"""

import sys, asyncio, threading, signal, time, logging
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from io import TextIOWrapper
from typing import Optional, Callable
from util import my_name

#———————————————————————————————————————————————————————————————————————————————

class ShutdownManager:

	"""
	Centralized shutdown manager that handles graceful application 
	termination.
	
	Features:
	- Thread-safe shutdown state management
	- Proper resource cleanup (files, executors)
	- Signal handler registration
	- Prevents duplicate shutdown attempts
	"""
	
	#———————————————————————————————————————————————————————————————————————————
	
	def __init__(
		self,
		logger: logging.Logger
	):
		
		self.logger = logger
		self._lock  = threading.Lock()

		self._shutdown_complete = False
		self._shutdown_event	= threading.Event()
		
		self._executors:	dict[str, ProcessPoolExecutor] = {}
		self._file_handles:	dict[str, tuple[str, TextIOWrapper]] = {}

		self._symbols:		 list = []
		self._asyncio_tasks: list = []

		self._custom_cleanup_callbacks:	list = []
	
	#———————————————————————————————————————————————————————————————————————————
	
	def register_asyncio_tasks(self, *tasks: asyncio.Task) -> None:

		"""
		Register asyncio tasks for graceful cancellation and exception handling.
		"""

		with self._lock:

			self._asyncio_tasks.extend(tasks)
			
			for task in tasks:

				task.add_done_callback(
					self._handle_task_completion
				)

	#———————————————————————————————————————————————————————————————————————————
	
	def _handle_task_completion(self, task: asyncio.Task) -> None:

		"""
		Handle task completion and consume any exceptions to prevent
		'Task exception was never retrieved' warnings.
		"""

		try:
			
			task.result()

		except Exception as e:
			
			self.logger.warning(
				f"[{my_name()}] Task {task.get_name()} completed with "
				f"exception (already logged by decorator): "
				f"{type(e).__name__}"
			)

		except asyncio.CancelledError:
			
			self.logger.info(
				f"[{my_name()}] Task "
				f"{task.get_name()} was cancelled"
			)

	#———————————————————————————————————————————————————————————————————————————

	def cancel_asyncio_tasks(
		self
	) -> None:

		"""
		Cancel all registered asyncio tasks gracefully.
		Exception handling is already done by done callbacks.
		"""

		if not self._asyncio_tasks: return
		
		self.logger.info(
			f"[{my_name()}] Cancelling "
			f"{len(self._asyncio_tasks)} asyncio tasks..."
		)
		
		for task in self._asyncio_tasks:

			try:

				if not task.done():

					task.cancel()
					self.logger.info(
						f"[{my_name()}] "
						f"Cancelled task: {task.get_name()}"
					)

			except Exception as e:

				self.logger.warning(
					f"[{my_name()}] "
					f"Failed to cancel task: {e}"
				)
		
		try:
			
			loop = asyncio.get_running_loop()
			if loop and not loop.is_closed():
				
				self.logger.info(
					f"[{my_name()}] "
					f"All task exceptions handled by callbacks"
				)

		except Exception as e:

			self.logger.warning(
				f"[{my_name()}] Task cleanup info: {e}"
			)

	#———————————————————————————————————————————————————————————————————————————

	def _wait_for_task_cancellation(self):

		"""Helper to wait for task cancellation in separate thread."""

		try:
			
			try:

				loop = asyncio.get_running_loop()

			except RuntimeError:
				
				loop = asyncio.new_event_loop()
				asyncio.set_event_loop(loop)
			
			if loop and not loop.is_closed():

				try:

					pending_tasks = [
						t for t in self._asyncio_tasks
						if not t.done()
					]

					if pending_tasks:

						async def wait_tasks():

							try:
								await asyncio.wait_for(
									asyncio.wait(
										pending_tasks, 
										return_when=asyncio.ALL_COMPLETED
									),
									timeout=1.0
								)

							except asyncio.TimeoutError:

								self.logger.warning(
									"Task cancellation wait timed out"
								)

							except Exception:
								pass
						
						if loop.is_running():
							
							task = loop.create_task(wait_tasks())
							time.sleep(0.1)

						else:

							loop.run_until_complete(wait_tasks())

				except Exception as e:

					self.logger.warning(
						f"Task cancellation wait error: {e}"
					)

		except Exception as e:

			self.logger.warning(
				f"_wait_for_task_cancellation error: {e}"
			)

	#———————————————————————————————————————————————————————————————————————————

	def register_executors(
		self, 
		**executors: ProcessPoolExecutor
	) -> None:

		"""
		Register executors for shutdown management.
		
		Args:
			**executors: Named executors (e.g., merge_executor=executor)
		"""
		
		with self._lock:

			self._executors.update(executors)
	
	#———————————————————————————————————————————————————————————————————————————
	
	def register_file_handles(
		self, 
		file_handles: dict[str, tuple[str, TextIOWrapper]]
	) -> None:

		"""
		Register file handles for cleanup.
		
		Args:
			file_handles: dict mapping symbols to (suffix, writer) tuples
		"""
		
		with self._lock:

			self._file_handles = file_handles
	
	#———————————————————————————————————————————————————————————————————————————
	
	def register_symbols(
		self,
		symbols: list
	) -> None:

		"""
		Register symbols list for file cleanup.
		
		Args:
			symbols: List of trading symbols
		"""
		
		with self._lock:

			self._symbols = symbols.copy()
	
	#———————————————————————————————————————————————————————————————————————————
	
	def add_cleanup_callback(
		self, 
		callback: Callable[[], None]
	) -> None:

		"""
		Add custom cleanup callback to be executed during shutdown.
		
		Args:
			callback: Callable that performs cleanup operations
		"""
		
		with self._lock:

			self._custom_cleanup_callbacks.append(callback)
	
	#———————————————————————————————————————————————————————————————————————————
	
	def is_shutdown_complete(
		self
	) -> bool:

		"""
		Check if shutdown has been completed.
		"""
		
		with self._lock:

			return self._shutdown_complete
	
	#———————————————————————————————————————————————————————————————————————————
	
	def shutdown_executors(
		self
	) -> None:

		"""
		Gracefully shutdown all registered executors with individual 
		logging. Thread-safe and prevents duplicate shutdown attempts.
		"""
		
		# Get executors copy with lock, then release lock before shutdown
		
		with self._lock:

			executors_copy = dict(self._executors)
		
		for name, executor in executors_copy.items():
			
			try:
				
				if executor:
					
					self.logger.info(
						f"[{my_name()}] Shutting down "
						f"{name.upper()}_EXECUTOR..."
					)
					
					executor.shutdown(wait=True)
					
					self.logger.info(
						f"[{my_name()}] {name.upper()}_EXECUTOR "
						f"shutdown safely complete."
					)
			
			except Exception as e:
				
				self.logger.error(
					f"[{my_name()}] {name.upper()}_EXECUTOR "
					f"shutdown failed: {e}",
					exc_info=True
				)
	
	#———————————————————————————————————————————————————————————————————————————
	
	def close_file_handles(self) -> None:
		
		"""
		Close all registered file handles safely.
		"""
		
		# Get data copies with lock, then release lock before file operations
		
		with self._lock:

			symbols_copy = list(self._symbols)
			file_handles_copy = dict(self._file_handles)
		
		for symbol in symbols_copy:
			
			suffix_writer = file_handles_copy.get(symbol)
			
			if suffix_writer:
				
				suffix, writer = suffix_writer
				
				try:
					
					if writer and not writer.closed: writer.close()
					
					self.logger.info(
						f"[{my_name()}] Closed file for "
						f"{symbol}"
					)
				
				except Exception as e:
					
					self.logger.error(
						f"[{my_name()}] "
						f"Failed to close file for "
						f"{symbol}: {e}"
					)
	
	#———————————————————————————————————————————————————————————————————————————
	
	def run_custom_cleanup(
		self
	) -> None:

		"""
		Execute all registered custom cleanup callbacks.
		"""
		
		for callback in self._custom_cleanup_callbacks:
			
			try: callback()

			except Exception as e:
				
				self.logger.error(
					f"[{my_name()}] Custom "
					f"cleanup callback failed: {e}",
					exc_info=True
				)
	
	#———————————————————————————————————————————————————————————————————————————

	def register_shutdown_event(self, shutdown_event: asyncio.Event) -> None:
		"""외부 shutdown_event를 등록하여 종료 시 함께 설정"""
		with self._lock:
			if not hasattr(self, '_external_shutdown_events'):
				self._external_shutdown_events = []
			self._external_shutdown_events.append(shutdown_event)

	#———————————————————————————————————————————————————————————————————————————
	
	def graceful_shutdown(self) -> None:
		"""Complete graceful shutdown sequence."""
		with self._lock:
			if self._shutdown_complete:
				return
		
		try:
			self.logger.info(f"[{my_name()}] Starting graceful shutdown...")
			
			# Force exit timer 시작 (개선된 버전)
			def force_exit_timer():
				time.sleep(10.0)
				if not self._shutdown_complete:  # ✅ 완료 상태 확인 추가
					print("[FORCE EXIT] Graceful shutdown timeout - forcing exit")
					self.logger.warning(f"[{my_name()}] Graceful shutdown timeout - forcing exit")
					import os
					os._exit(1)
			
			timer_thread = threading.Thread(target=force_exit_timer, daemon=True)
			timer_thread.start()
			
			# 1. Set shutdown event to signal other components
			self._shutdown_event.set()

			# 2. Set external shutdown events (스레드 안전하게)
			with self._lock:
				if hasattr(self, '_external_shutdown_events'):
					external_events = list(self._external_shutdown_events)  # 복사본 생성
			
			# 락 해제 후 이벤트 설정
			if 'external_events' in locals():
				for event in external_events:
					try:
						if not event.is_set():
							event.set()
					except Exception as e:
						self.logger.warning(f"Failed to set external shutdown event: {e}")

			
			# 3. Run custom cleanup callbacks (먼저 실행)
			self.run_custom_cleanup()
			
			# 4. Brief delay to allow cleanup tasks to start
			time.sleep(0.1)
			
			# 5. Cancel asyncio tasks (cleanup 후 실행)
			self.cancel_asyncio_tasks()
			
			# 6. Close all file handles
			self.close_file_handles()
			
			# 7. Shutdown executors
			self.shutdown_executors()
			
			# 8. Mark shutdown as complete (✅ 타이머 무력화)
			with self._lock:
				self._shutdown_complete = True
			
			self.logger.info(f"[{my_name()}] Graceful shutdown completed.")

			print(f"[DEBUG] ShutdownManager.graceful_shutdown completed at {time.time()}")

			# 추가: 활성 태스크 수 확인
			try:
				loop = asyncio.get_running_loop()
				if loop:
					active_tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
					print(f"[DEBUG] Active tasks remaining: {len(active_tasks)}")
					for i, task in enumerate(active_tasks[:5]):  # 처음 5개만 표시
						print(f"[DEBUG] Active task {i+1}: {task.get_name()}")
			except:
				print("[DEBUG] Could not check active tasks")
			
		except Exception as e:
			self.logger.error(f"[{my_name()}] Error during shutdown: {e}")
			with self._lock:
				self._shutdown_complete = True

	#———————————————————————————————————————————————————————————————————————————

	def is_shutting_down(
		self
	) -> bool:

		"""
		Check if shutdown process has been initiated.
		This can be used by other components to stop gracefully.
		"""

		return self._shutdown_event.is_set()
	
	#———————————————————————————————————————————————————————————————————————————
	
	def signal_handler(
		self,
		signum: int,
		frame
	) -> None:

		"""
		Signal handler for SIGINT/SIGTERM with duplicate call prevention.
		"""

		if self.is_shutting_down():

			self.logger.info(
				f"[{my_name()}] Signal {signum} ignored "
				f"- shutdown already in progress"
			)
			return
		
		self.logger.info(
			f"[{my_name()}] Received signal {signum}. "
			f"Initiating shutdown..."
		)
		
		# Perform graceful shutdown
		self.graceful_shutdown()
		
		# Exit cleanly
		sys.exit(0)
	
	#———————————————————————————————————————————————————————————————————————————
	
	def register_signal_handlers(self) -> None:

		"""
		Register signal handlers for graceful shutdown.
		"""
		
		signal.signal(signal.SIGINT, self.signal_handler)
		signal.signal(signal.SIGTERM, self.signal_handler)
		
		self.logger.info(
			f"[{my_name()}] 📡 SIGINT/SIGTERM"
		)

#———————————————————————————————————————————————————————————————————————————————

def create_shutdown_manager(
	logger: logging.Logger
) -> ShutdownManager:
	
	"""
	Create and return a new ShutdownManager instance.
	
	Args:
		logger: Logger instance for shutdown operations
		
	Returns:
		Configured ShutdownManager instance
	"""
	
	return ShutdownManager(logger)

#———————————————————————————————————————————————————————————————————————————————