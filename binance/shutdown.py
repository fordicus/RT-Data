import sys, os, asyncio, threading, signal, time, logging
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
from io import TextIOWrapper
from typing import Optional, Callable
from util import my_name

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

	def __init__(self, logger: logging.Logger):

		self.logger = logger
		self._lock = threading.Lock()
		self._shutdown_complete = False
		self._executors: dict[str, ProcessPoolExecutor] = {}
		self._file_handles: dict[str, tuple[str, TextIOWrapper]] = {}
		self._symbols: list = []
		self._shutdown_event: Optional[asyncio.Event] = None
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

	def register_shutdown_event(
		self,
		shutdown_event: asyncio.Event
	) -> None:

		self._shutdown_event = shutdown_event

	#———————————————————————————————————————————————————————————————————————————

	def register_executors(
		self,
		**executors: ProcessPoolExecutor
	) -> None:

		with self._lock:

			self._executors.update(executors)

	#———————————————————————————————————————————————————————————————————————————

	def register_file_handles(
		self, file_handles: dict[str,
		tuple[str, TextIOWrapper]]
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

		return self._shutdown_event and self._shutdown_event.is_set()

	#———————————————————————————————————————————————————————————————————————————

	def close_file_handles(self) -> None:
		
		with self._lock:
			
			symbols_copy = list(self._symbols)
			file_handles_copy = dict(self._file_handles)
		
		for symbol in symbols_copy:

			suffix_writer = file_handles_copy.get(symbol)

			if suffix_writer:

				suffix, writer = suffix_writer

				try:

					if writer and not writer.closed:

						writer.flush()
						os.fsync(writer.fileno())
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

					self.logger.info(
						f"[{my_name()}] "
						f"shutting down "
						f"{name.upper()}_EXECUTOR..."
					)

					start_time = time.time()
					executor.shutdown(wait=True)
					elapsed = time.time() - start_time

					self.logger.info(
						f"[{my_name()}] "
						f"{name.upper()}_EXECUTOR "
						f"shut down in {elapsed:.5f}s"
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
) -> ShutdownManager:

	return ShutdownManager(logger)

#———————————————————————————————————————————————————————————————————————————————
