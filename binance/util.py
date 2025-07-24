# util.py

#———————————————————————————————————————————————————————————————————————————————

import sys, os, time, inspect, logging, multiprocessing
import asyncio, uvloop
import aiohttp, socket
from functools import lru_cache
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener
from typing import Callable, Optional

#———————————————————————————————————————————————————————————————————————————————
# Technical Utilities
#———————————————————————————————————————————————————————————————————————————————

def my_name() -> str:

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

async def is_uvloop_alive() -> bool:

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

#———————————————————————————————————————————————————————————————————————————————

def ms_to_datetime(ms: int) -> datetime:

	"""
	Converts a millisecond timestamp to a UTC datetime object.
	"""

	return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

#———————————————————————————————————————————————————————————————————————————————

def compute_bias_ms(
	ts_now_ms: int,
	target_dt: datetime
) -> int:

	"""
	Computes the millisecond bias between a given UTC timestamp (ms) and
	a target datetime.

	Args:
	
		ts_now_ms (int):
			Current timestamp in milliseconds (UTC).

		target_dt (datetime):
			Target datetime in UTC. If naive, it's assumed to be UTC.

	Example Input:

		ts_now_ms = get_current_time_ms()
		target_dt = datetime(2025, 7, 25, 21, 59)

	Returns:
		int: Millisecond difference (bias_ms) = target - now
	"""

	# Convert timestamp to datetime (UTC)

	now_dt = ms_to_datetime(ts_now_ms)

	# If target is naive (unknown timezone), assume UTC

	if target_dt.tzinfo is None:

		target_dt = target_dt.replace(
			tzinfo=timezone.utc
		)

	# Compute difference in milliseconds
	
	bias_ms = int(
		(target_dt - now_dt).total_seconds() * 1000
	)

	return bias_ms

"""—————————————————————————————————————————————————————————————————————————————
	with NanoTimer() as timer:
		print(
			f"[{my_name()}] took {timer.tock():.5f} sec.",
			flush=True,
		)
—————————————————————————————————————————————————————————————————————————————"""

class NanoTimer:

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
# Web Utilities
#———————————————————————————————————————————————————————————————————————————————

@lru_cache(maxsize=256)						# cache to hit the API once per IP
async def geo(ip: str) -> str:

	"""
	Return 'City, Country' (or '?' if unknown) for a public IP.
	Uses the free ip-api.com JSON endpoint (≈ 45 ms median, no key required).
	"""

	url = (
		f"http://ip-api.com/json/{ip}?fields=city,country"
	)   # :contentReference[oaicite:0]{index=0}

	try:

		async with aiohttp.ClientSession(
			timeout=aiohttp.ClientTimeout(total=2)
		) as s:

			async with s.get(url) as r:

				if r.status == 200:

					data = await r.json()
					return (
						f"{data.get('city') or '?'} "
						f"{data.get('country') or ''}".strip()
					)

    except Exception as e:

        try:

            logger = get_subprocess_logger()
            logger.warning(
				f"[{my_name()}] IP geolocation failed for {ip}: {e}"
			)

        except Exception:

			force_print_exception(
				my_name(), e
			)

	# fallback: try reverse‑DNS for AWS / GCP hosts (region code often embedded)

	try:

		# :contentReference[oaicite:1]{index=1}
		host, *_ = socket.gethostbyaddr(ip)

		# e.g. ec2‑54‑250‑75‑34.ap‑northeast‑1.compute.amazonaws.com
		# →  ap‑northeast‑1 (Tokyo)

		if ".compute.amazonaws.com" in host:

			region = host.split(".")[-4]	# ap‑northeast‑1
			return region.replace("-", " ").title()

    except Exception as e:
		
        try:
            logger = get_subprocess_logger()
            logger.warning(
				f"[{my_name()}] DNS lookup failed for {ip}: {e}"
			)

        except Exception:

			force_print_exception(
				my_name(), e
			)

	return "?"

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

class UTCFormatter(logging.Formatter):

	#———————————————————————————————————————————————————————————————————————————
	# https://tinyurl.com/ANSI-256-Color-Palette
	#———————————————————————————————————————————————————————————————————————————

	COLOR_MAP = {
		'DEBUG':	'\033[38;5;242m',  # cool gray (low contrast, non-intrusive)
		'INFO':	 	'\033[38;5;34m',   # green (positive, success-like)
		'WARNING':  '\033[38;5;214m',  # orange (attention-grabbing, softer red)
		'ERROR':	'\033[38;5;196m',  # bright red (danger, strong error)
		'CRITICAL': '\033[38;5;199m',  # magenta red (urgent, dramatic)
	}
	RESET = '\033[0m'
	RESET = '\033[0m'

	def format(self, record):

		original_levelname = record.levelname
		color = self.COLOR_MAP.get(original_levelname, '')
		if color:
			record.levelname = f"{color}{original_levelname}{self.RESET}"
		
		formatted = super().format(record)

		record.levelname = original_levelname
		return formatted

	def formatTime(self, record, datefmt=None):

		# Convert record creation time to UTC datetime
		dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
		
		# Return formatted string based on optional format string
		if datefmt:
			return dt.strftime(datefmt)
		
		# Default to ISO 8601 format
		return dt.isoformat(timespec='microseconds')

#———————————————————————————————————————————————————————————————————————————————

def get_global_log_queue():

	if _global_log_queue is None:
		raise RuntimeError(
			f"[{datetime.now(timezone.utc).isoformat()}] "
			f"ERROR: [{my_name()}] Failed to initialize "
			f"_global_log_queue."
		)
	return _global_log_queue	# multiprocessing.Queue

#———————————————————————————————————————————————————————————————————————————————

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

async def force_flush_logger(
	logger: logging.Logger,
):

	#———————————————————————————————————————————————————————————————————————————

	async def force_flush_queue(
		handler: QueueHandler,
	):
		while not handler.queue.empty():
			try:
				handler.queue.get_nowait()
			except Exception:
				break
			await asyncio.sleep(0)

	#———————————————————————————————————————————————————————————————————————————
	
	try:

		for handler in logger.handlers:

			if hasattr(handler, 'flush'):
				handler.flush()
			
			if isinstance(handler, QueueHandler):
				await force_flush_queue(handler)

	except Exception as e:

		print(
			f"[{my_name()}] {e}",
			file=sys.stderr,
			flush=True
		)

"""—————————————————————————————————————————————————————————————————————————————
@ensure_logging_on_exception
def your_function():
	...
—————————————————————————————————————————————————————————————————————————————"""

def ensure_logging_on_exception(
	coro_func: Callable,
):

	"""
	Decorator that guarantees exception logging with minimal overhead.
	Uses the established global logger system via `get_subprocess_logger()`.
	Only activates when exceptions occur - zero cost during normal operation.
	"""

	async def wrapper(
		*args, **kwargs
	):

		try:

			return await coro_func(*args, **kwargs)

		except Exception as e:

			try:

				logger = get_subprocess_logger()

			except Exception:

				logger = logging.getLogger()
			
			logger.critical(
				f"{coro_func.__name__} failed: {e}",
				exc_info=True
			)

			await force_flush_logger(logger)
			
			raise

	wrapper.__name__ = coro_func.__name__
	wrapper.__doc__ = coro_func.__doc__
	return wrapper

#———————————————————————————————————————————————————————————————————————————————

def force_print_exception(
	scope_name: str,
	e: Optional[Exception] = None, 
):

	try:

		print(
			f"[{scope_name}] {e or 'Unknown exception'}",
			file=sys.stderr,
			flush=True
		)

	except Exception:

		pass  # even this shouldn't fail

#———————————————————————————————————————————————————————————————————————————————