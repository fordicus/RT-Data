# shutdown.py @2025-08-07 18:09 / DO NOT BLINDLY MODIFY THIS CODE

import sys, os, asyncio, threading, signal, time, logging, copy
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from io import TextIOWrapper
from typing import Optional, Callable
from util import my_name
from hotswap import HotSwapManager

class ShutdownManager:

	#———————————————————————————————————————————————————————————————————————————

	def final_message(self) -> None:
		
		with self._lock:

			if not self._final_message_printed:

				self._final_message_printed = True
				self.logger.info(
					f"[{my_name()}] おつかれさまでございます。"
				)
				
				for handler in self.logger.handlers:
					
					handler.flush()

	#———————————————————————————————————————————————————————————————————————————

	def __init__(self, 
		logger: logging.Logger
	):

		self.logger = logger
		self._lock = threading.Lock()
		self._shutdown_complete = False
		self._executors: dict[str, ProcessPoolExecutor] = {}
		self._file_handles: list[
			dict[str, tuple[str, TextIOWrapper]]
		] = []
		self._symbols: list = []
		self._shutdown_event: asyncio.Event = asyncio.Event()
		# self._shutdown_event: Optional[asyncio.Event] = None
		self._custom_cleanup_callbacks:	list = []
		self._final_message_printed = False

	#———————————————————————————————————————————————————————————————————————————

	def add_cleanup_callback(
		self,
		callback: Callable[[], None]
	) -> None:
		
		with self._lock:

			self._custom_cleanup_callbacks.append(callback)

	#———————————————————————————————————————————————————————————————————————————

	def run_custom_cleanup(self) -> None:

		for callback in self._custom_cleanup_callbacks:

			try: callback()

			except Exception as e:

				self.logger.error(
					f"[{my_name()}] custom "
					f"cleanup callback failed: {e}",
					exc_info=True
				)

	#———————————————————————————————————————————————————————————————————————————

	# def register_shutdown_event(
	# 	self,
	# 	shutdown_event: asyncio.Event
	# ) -> None:

	# 	self._shutdown_event = shutdown_event

	#———————————————————————————————————————————————————————————————————————————

	def register_executors(self,
		**executors: ProcessPoolExecutor,
	) -> None:

		with self._lock:

			self._executors.update(executors)

	#———————————————————————————————————————————————————————————————————————————

	def register_file_handles(self,
		file_handles: list[
			dict[str, tuple[str, TextIOWrapper]]
		]
	) -> None:

		with self._lock:

			self._file_handles = file_handles

	#———————————————————————————————————————————————————————————————————————————

	def register_symbols(self, symbols: list) -> None:

		with self._lock:

			self._symbols = symbols.copy()

	#———————————————————————————————————————————————————————————————————————————

	def is_shutdown_complete(self) -> bool:

		with self._lock:

			return self._shutdown_complete

	#———————————————————————————————————————————————————————————————————————————

	def is_shutting_down(self) -> bool:

		return (
			self._shutdown_event
			and self._shutdown_event.is_set()
		)

	#———————————————————————————————————————————————————————————————————————————

	def close_file_handles(self) -> None:

		with self._lock:

			symbols_snapshot   = tuple(self._symbols)
			file_maps_snapshot = [
				fhc.copy()
				for fhc in self._file_handles
			]

		for fhc in file_maps_snapshot:  # dict in list

			for symbol in symbols_snapshot:

				suffix_writer = fhc.get(symbol)

				if not suffix_writer: continue

				suffix, writer = suffix_writer

				try:

					if (
						writer
						and not writer.closed
					):

						writer.flush()

						try:

							os.fsync(writer.fileno())
							
						except (OSError, AttributeError):
							
							pass

						writer.close()

					self.logger.info(
						f"[{my_name()}]💾 "
						f"{symbol.upper()} safely closes"
					)

				except Exception as e:

					self.logger.error(
						f"[{my_name()}]💾 "
						f"failed to close "
						f"{symbol.upper()}: {e}"
					)

	#———————————————————————————————————————————————————————————————————————————

	def shutdown_executors(self) -> None:
		
		with self._lock:
			executors_copy = dict(self._executors)
		
		for name, executor in executors_copy.items():

			try:

				if executor:

					start_time = time.time()
					executor.shutdown(wait=True)
					elapsed = time.time() - start_time

					self.logger.info(
						f"[{my_name()}] "
						f"{name.upper()}_EXECUTOR "
						f"shut down in {elapsed * 1000.:.3f}ms"
						)

			except Exception as e:

				self.logger.error(
					f"[{my_name()}] "
					f"{name.upper()}_EXECUTOR "
					f"shutdown failed: {e}"
				)

	#———————————————————————————————————————————————————————————————————————————

	def graceful_shutdown(self) -> None:
		
		with self._lock:
			if self._shutdown_complete:
				return
		
		try:

			self.logger.info(f"[{my_name()}] starts")
			
			if self._shutdown_event:

				self._shutdown_event.set()

			self.shutdown_executors()
			self.close_file_handles()
			self.run_custom_cleanup()
			
			with self._lock:

				self._shutdown_complete = True
			
			self.logger.info(f"[{my_name()}] completes")
			
		except Exception as e:

			self.logger.error(
				f"[{my_name()}] error during shutdown: {e}"
			)

			with self._lock:
				self._shutdown_complete = True

	#———————————————————————————————————————————————————————————————————————————

	def signal_handler(
		self,
		signum: int,
		frame
	) -> None:
		
		if self.is_shutting_down():

			self.logger.info(
				f"[{my_name()}] signal-{signum} ignored: "
				f"shutdown already in progress"
			)
			return
		
		self.logger.info(
			f"[{my_name()}] received signal {signum}. "
			f"initiating shutdown..."
		)
		self.graceful_shutdown()
		sys.exit(0)

	#———————————————————————————————————————————————————————————————————————————

	def register_signal_handlers(self) -> None:

		signal.signal(signal.SIGINT, self.signal_handler)
		signal.signal(signal.SIGTERM, self.signal_handler)
		self.logger.info(f"[{my_name()}]📡 SIGINT/SIGTERM")

#———————————————————————————————————————————————————————————————————————————————

def create_shutdown_manager(
	logger: logging.Logger
) -> tuple[ShutdownManager, asyncio.Event]:

	shutdown_manager = ShutdownManager(logger)

	return (
		shutdown_manager,
		shutdown_manager._shutdown_event,
	)

#———————————————————————————————————————————————————————————————————————————————

async def generic_shutdown_callback(
	hotswap_manager:  HotSwapManager,
	shutdown_manager: ShutdownManager,
	logger:			  logging.Logger,
) -> None:

	"""
	Generic shutdown callback that can be used in any script.
	
	Args:
		hotswap_manager: The HotSwapManager instance to shutdown gracefully
		shutdown_manager: The ShutdownManager instance for final cleanup
		logger: Logger for output messages
	"""
	
	async def wait_and_print_final(
		shutdown_manager: ShutdownManager,
		cleanup_task:	  asyncio.Task,
		logger:			  logging.Logger,
	) -> None:

		"""
		Wait for cleanup task completion and print final message.
		
		Args:
			shutdown_manager: ShutdownManager instance for final message
			cleanup_task: The hotswap cleanup task to wait for
			logger: Logger for error messages
		"""

		try:

			await cleanup_task

		except Exception as e:

			logger.error(
				f"[{my_name()}] "
				f"Hotswap cleanup error: {e}"
			)

		finally:

			shutdown_manager.final_message()

	# Log the shutdown initiation

	logger.info(
		f"[{my_name()}] {hotswap_manager.name} @main"
	)

	if hotswap_manager:

		try:

			loop = asyncio.get_running_loop()

			if loop and not loop.is_closed():
				cleanup_task = loop.create_task(
					hotswap_manager.graceful_shutdown(logger)
				)
				
				asyncio.create_task(
					wait_and_print_final(
						shutdown_manager,
						cleanup_task,
						logger,
					)
				)

		except Exception as e:

			logger.error(
				f"[{my_name()}] {hotswap_manager.name}: {e}"
			)

			shutdown_manager.final_message()
	else:

		shutdown_manager.final_message()

#———————————————————————————————————————————————————————————————————————————————

def create_shutdown_callback(
	hotswap_manager: HotSwapManager,
	shutdown_manager: ShutdownManager,
	logger: logging.Logger,
) -> callable:

	def shutdown_callback() -> None:

		try:

			loop = asyncio.get_running_loop()

			if loop and not loop.is_closed():

				asyncio.create_task(
					generic_shutdown_callback(
						hotswap_manager,
						shutdown_manager,
						logger,
					)
				)

		except RuntimeError:

			# No event loop running, call final message directly
			shutdown_manager.final_message()
	
	return shutdown_callback

#———————————————————————————————————————————————————————————————————————————————