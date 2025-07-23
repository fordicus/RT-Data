# util.py

#———————————————————————————————————————————————————————————————————————————————

import sys, os, time, inspect, logging, multiprocessing
import asyncio, uvloop

from datetime import datetime, timezone

#———————————————————————————————————————————————————————————————————————————————
# Technical Utilities
#———————————————————————————————————————————————————————————————————————————————

def my_name():
	frame = inspect.stack()[1]
	return f"{frame.function}:{frame.lineno}"

#———————————————————————————————————————————————————————————————————————————————

def resource_path(	# Resource Resolver for PyInstaller
	relative_path:	str,
	logger: logging.RootLogger = None,
) -> str:

	try:

		if logger is not None:
			
			if not isinstance(logger, logging.Logger):

				raise TypeError(
					f"logger must be an instance of "
					f"logging.Logger"
				)

			logger.info(
				f"[{my_name()}] Called with "
				f"relative_path='{relative_path}'"
			)

		if hasattr(sys, "_MEIPASS"):		# PyInstaller
			
			base_path = sys._MEIPASS
			
		elif "__compiled__" in globals():	# Nuitka
			
			import nuitka.__main__
			base_path = os.path.dirname(sys.executable)
			
		else:
			
			base_path = os.path.abspath(".")
			
		return os.path.join(
			base_path, relative_path
		)

	except Exception as e:

		raise RuntimeError(
			f"[{my_name()}] Failed to "
			f"resolve path: {relative_path}"
		) from e

#———————————————————————————————————————————————————————————————————————————————

def get_event_loop_info() -> bool:

	try:

		loop = asyncio.get_running_loop()
		return (
			isinstance(loop, uvloop.Loop)
			and loop.is_running()
			and not loop.is_closed()
		)

	except RuntimeError:
		
		return False

#———————————————————————————————————————————————————————————————————————————————
# Time Utilities
#———————————————————————————————————————————————————————————————————————————————

def get_current_time_ms() -> int:

	"""
	Returns the current time in milliseconds as an integer.
	Uses nanosecond precision for maximum accuracy.
	"""

	return time.time_ns() // 1_000_000

def ms_to_datetime(ms: int) -> datetime:

	"""
	Converts a millisecond timestamp to a UTC datetime object.
	"""

	return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

class NanoTimer:

	"""
	A class for high-precision timing using nanoseconds.
	Provides methods to record a start time (tick) and calculate
	the elapsed time in seconds (tock).
	"""

	def __init__(self, reset_on_instantiation: bool = True):

		self.start_time_ns = (
			time.time_ns() if reset_on_instantiation else None
		)

	def tick(self):
		
		self.start_time_ns = time.time_ns()

	def tock(self) -> float:

		"""
		Calculates the elapsed time in seconds since the last tick.

		Returns:
			float: Elapsed time in seconds.
		Raises:
			ValueError: If tick() has not been called before tock().
		"""

		if self.start_time_ns is None:

			raise ValueError("tick() must be called before tock().")

		elapsed_ns = time.time_ns() - self.start_time_ns

		return elapsed_ns / 1_000_000_000.0

	def __enter__(self):

		self.tick()

		return self

	def __exit__(self, exc_type, exc_value, traceback):

		pass

#———————————————————————————————————————————————————————————————————————————————

def format_ws_url(
	url: str, label: str = ""
) -> str:

	"""
	Formats a Binance WebSocket URL for multi-symbol readability.
	Example:
		wss://stream.binance.com:9443/stream?streams=
			btcusdc@depth/
			ethusdc@depth/
			solusdc@depth (@depth)
	"""

	if "streams=" not in url:

		return url + (f" {label}" if label else "")

	prefix, streams = url.split("streams=", 1)
	symbols = streams.split("/")
	formatted = "\t" + prefix + "streams=\n"
	formatted += "".join(f"\t\t{s}/\n" for s in symbols if s)
	formatted = formatted.rstrip("/\n")

	if label:

		formatted += f" {label}"

	return formatted

#———————————————————————————————————————————————————————————————————————————————
# Unified Process-Agnostic Logger
#———————————————————————————————————————————————————————————————————————————————
# Any Process
# → QueueHandler
# → QueueListener
# → Flush One Time (RotatingFileHandler + StreamHandler)
#———————————————————————————————————————————————————————————————————————————————

_global_log_queue = None

from logging.handlers import QueueListener

class UTCFormatter(logging.Formatter):

	def formatTime(self, record, datefmt=None):

		# Convert record creation time to UTC datetime
		dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
		
		# Return formatted string based on optional format string
		if datefmt:
			return dt.strftime(datefmt)
		
		# Default to ISO 8601 format
		return dt.isoformat(timespec='microseconds')

def get_global_log_queue():

	if _global_log_queue is None:
		raise RuntimeError(
			f"[{datetime.now(timezone.utc).isoformat()}] "
			f"ERROR: [{my_name()}] Failed to initialize "
			f"_global_log_queue."
		)
	return _global_log_queue	# multiprocessing.Queue

#———————————————————————————————————————————————————————————————————————————————

from logging.handlers import QueueHandler

def set_global_logger(
	filename:	  str = "stream_binance.log",
	maxBytes:	  int = 10_485_760,		# Rotate after 10 MB
	backupCount:  int = 100,			# Keep # of backups
	logLevel:	  int = logging.INFO,
) -> (
	logging.Logger,		# logger.error(), etc
	QueueListener		# queue_listener.stop()
):

	#———————————————————————————————————————————————————————————————————————————

	from logging.handlers import RotatingFileHandler

	def set_global_log_queue(
		queue: multiprocessing.Queue
	):
		global _global_log_queue
		_global_log_queue = queue

	#———————————————————————————————————————————————————————————————————————————
	# DO NOT CARELESSLY ATTEMPT TO MODIFY THE BELOW
	#———————————————————————————————————————————————————————————————————————————

	try:

		loggingStreamHandler = logging.StreamHandler()
		loggingRotatingFileHandler = RotatingFileHandler(
			filename	= filename,
			mode		= "a",
			maxBytes	= maxBytes,
			backupCount = backupCount,
			encoding	= "utf-8",
		)

		mp_log_queue = multiprocessing.Queue()
		queue_listener = QueueListener(
			mp_log_queue,
			loggingRotatingFileHandler,
			loggingStreamHandler
		)

		logger = logging.getLogger()
		logger.handlers.clear()
		logger.setLevel(logLevel)

		queue_listener.start()
		set_global_log_queue(mp_log_queue)
		logger.addHandler(
			QueueHandler(mp_log_queue)
		)

		#———————————————————————————————————————————————————————————————————————
		# Uvicorn & FastAPI: WARNING
		#———————————————————————————————————————————————————————————————————————

		for name in [
			"fastapi", "uvicorn",
			"uvicorn.error",
			"uvicorn.access"
		]:
			
			specific_logger = logging.getLogger(name)
			specific_logger.setLevel(logging.WARNING)
			specific_logger.propagate = True

		#———————————————————————————————————————————————————————————————————————
		# All Others: INFO
		#———————————————————————————————————————————————————————————————————————

		for name in [
			"websockets",
			"websockets.server",
			"websockets.client",
			"starlette",
			"asyncio",
			"concurrent.futures"
		]:
			individual_logger = logging.getLogger(name)
			individual_logger.setLevel(logging.INFO)
			individual_logger.propagate = True
		
		for handler in logger.handlers:
			handler.setFormatter(
				UTCFormatter(
					"[%(asctime)s] %(levelname)s: %(message)s"
				)
			)

		return logger, queue_listener

	except Exception as e:

		print(
			f"[{datetime.now(timezone.utc).isoformat()}] "
			f"ERROR: [{my_name()}] Failed to "
			f"initialize logging: {e}",
			file  = sys.stderr,
			flush = True
		)
		sys.exit(1)

#———————————————————————————————————————————————————————————————————————————————

def get_subprocess_logger(
	mp_log_queue: multiprocessing.Queue = None,
	logLevel: int = logging.INFO,
) -> logging.Logger:
	
	log_queue = mp_log_queue or get_global_log_queue()
	
	if log_queue is None:

		raise RuntimeError(
			f"[{datetime.now(timezone.utc).isoformat()}] "
			f"ERROR: [{my_name()}] "
			f"log_queue is None"
		)
		sys.exit(1)
	
	subprocess_logger = logging.getLogger()
	subprocess_logger.setLevel(logLevel)
	
	if not any(
		isinstance(handler, QueueHandler)
		for handler in subprocess_logger.handlers
	):
		raise RuntimeError(
			f"[{datetime.now(timezone.utc).isoformat()}] "
			f"ERROR: [{my_name()}] "
			f"log_queue is None"
		)
		sys.exit(1)

	return subprocess_logger

#———————————————————————————————————————————————————————————————————————————————