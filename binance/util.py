# util.py

#———————————————————————————————————————————————————————————————————————————————

import sys, os, time, inspect, logging, multiprocessing
import asyncio, uvloop
import aiohttp, socket
import ssl, certifi
from functools import lru_cache
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener
from typing import Callable, Optional

#———————————————————————————————————————————————————————————————————————————
# https://tinyurl.com/ANSI-256-Color-Palette
#———————————————————————————————————————————————————————————————————————————

CMAP4TXT = {
	#
	'DEBUG':		'\033[38;5;242m',  # cool gray
	'INFO':	 		'\033[38;5;34m',   # green
	'WARNING':  	'\033[38;5;214m',  # orange
	'ERROR':		'\033[38;5;196m',  # bright red
	'CRITICAL': 	'\033[38;5;199m',  # magenta red
	#
	'CYBER TEAL':	'\033[38;2;35;209;110m',
	#
	'BLACK':		'\033[30m',
	'RED':			'\033[31m',
	'GREEN':		'\033[32m',
	'YELLOW':		'\033[33m',
	'BLUE':			'\033[34m',
	'MAGENTA':		'\033[35m',
	'CYAN':			'\033[36m',
	'WHITE':		'\033[37m',
	#
}
RESET4TXT = '\033[0m'

#———————————————————————————————————————————————————————————————————————————————
# Technical Utilities
#———————————————————————————————————————————————————————————————————————————————

def my_name() -> str:

	f = sys._getframe(1)
	try: return f"{f.f_code.co_name}:{f.f_lineno}"
	finally: del f

	# legacy style
	# frame = inspect.stack()[1]
	# return f"{frame.function}:{frame.lineno}"

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
				f"[{my_name()}]📂 {relative_path}"
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

_SSL_CTX = None

def get_ssl_context():

	global _SSL_CTX

	if _SSL_CTX is None:

		ctx = ssl.create_default_context(cafile=certifi.where())

		ctx.check_hostname = True
		ctx.verify_mode	   = ssl.CERT_REQUIRED

		_SSL_CTX = ctx

	return _SSL_CTX

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

	return datetime.fromtimestamp(ms / 1000.0, tz = timezone.utc)

#———————————————————————————————————————————————————————————————————————————————

def get_cur_datetime_str() -> str:

	dt = ms_to_datetime(
		get_current_time_ms()
	)
	
	return (
		dt.strftime("%Y-%m-%d %H:%M:%S.") 
		+ f"{dt.microsecond // 1000:03d}Z"
	)

#———————————————————————————————————————————————————————————————————————————————

def update_shared_time_dict(
	shared_time_dict: dict[str, float],
	key: str,
):

	shared_time_dict[key] = time.time()

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

@lru_cache(maxsize = 256)					# cache to hit the API once per IP
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
			timeout = aiohttp.ClientTimeout(total = 2)
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

async def elaborate_ws_peer(
	#
	ws_peer:	   dict[str, str],
	ws_ra:		   Optional[tuple[str, int]],
	logger:		   logging.Logger,
	ws_url_to_prt: str,
	timeout:	   float = 5.0,
	#
) -> None:

	if isinstance(ws_ra, tuple) and len(ws_ra) >= 2:

		ip, port = ws_ra[0], ws_ra[1]

	else:

		ip, port = "?", "?"

	try:

		if ip == "?": loc = "?"

		else:

			try:

				loc = await asyncio.wait_for(
					geo(ip), timeout = timeout,
				)

			except asyncio.TimeoutError:

				loc = "UNKNOWN"
				logger.warning(
					f"[{my_name()}] geo({ip}) timed out; "
					f"using fallback location",
					exc_info = False,
				)

	except asyncio.CancelledError: raise

	except Exception as e:

		loc = "UNKNOWN"

		if (
			isinstance(e, RuntimeError)
			and "cannot reuse already awaited coroutine" in str(e)
		):

			msg = "Coroutine reuse error, using fallback location"

		else:

			msg = f"Failed to get location for {ip}: {e}"

		logger.warning(f"[{my_name()}] {msg}", exc_info = False)

	ip_disp  = (
		f"[{ip}]"
		if (":" in ip and not ip.startswith("["))
		else ip
	)
	port_str = str(port)

	ws_peer["value"] = (
		f"{ip_disp}:{port_str}  ({loc})"
	)

	logger.info(
		f"[{my_name()}]🌐 "
		f"ws peer {ws_peer['value']}\n"
		f"  {ws_url_to_prt}"
	)

#———————————————————————————————————————————————————————————————————————————————

def format_ws_url(	# checks # of symbols 
	url: str, 
	symbols: list[str],
	ports_stream_binance_com: list[str] = None,
) -> str:

	#———————————————————————————————————————————————————————————————————————————

	def colorize_prefix(
		prefix: str,
		ports: list[str],
		color_code: str,
	) -> str:

		for port in ports:

			if port in prefix:

				colored = f"{color_code}{port}{RESET4TXT}"
				prefix = prefix.replace(port, colored, 1)
				break

		return prefix

	#———————————————————————————————————————————————————————————————————————————

	try:

		# If the number of symbols is less than 3, return the URL as-is

		if len(symbols) < 3:

			return url

		# Extract the prefix and streams from the URL

		if "streams=" not in url:

			return url  # Return as-is if the URL doesn't contain streams

		prefix, streams = url.split("streams=", 1)
		symbol_streams = streams.split("/")

		# Ensure the number of streams matches the number of symbols

		if len(symbol_streams) != len(symbols):

			raise ValueError(
				f"Mismatch between symbols and streams: "
				f"{len(symbols)} symbols, {len(symbol_streams)} streams."
			)

		# highlight the port number

		if ports_stream_binance_com is not None:

			prefix = colorize_prefix(
				prefix, 
				ports_stream_binance_com,
				CMAP4TXT.get('CYBER TEAL', "\033[33m"),
			)

		# Format the URL with the first and last symbols,
		# and "..." in the middle

		formatted = (
			f"{prefix}streams="
			f"{symbol_streams[0]}/.../{symbol_streams[-1]}"
		)

		return formatted

	except Exception as e:
		
		raise RuntimeError(
			f"[{my_name()}] Failed to format WebSocket URL: {e}"
		) from e

#———————————————————————————————————————————————————————————————————————————————

# def format_ws_url(	# does NOT check # of symbols 
# 	url: str,
# 	symbols: list[str],
# 	ports_stream_binance_com: list[str] = None,
# ) -> str:

# 	# ──────────────────────────────────────────────────────────────────────────
# 	def colorize_prefix(
# 		prefix: str,
# 		ports: list[str],
# 		color_code: str
# 	) -> str:

# 		for port in ports:

# 			if port in prefix:

# 				colored = f"{color_code}{port}{RESET4TXT}"
# 				prefix = prefix.replace(port, colored, 1)
# 				break

# 		return prefix
# 	# ──────────────────────────────────────────────────────────────────────────

# 	try:

# 		prefix_for_color = (
# 			url.split("streams=", 1)[0] if "streams=" in url else url
# 		)

# 		if ports_stream_binance_com is not None:
# 			prefix_for_color = colorize_prefix(
# 				prefix_for_color,
# 				ports_stream_binance_com,
# 				CMAP4TXT.get("CYBER TEAL", "\033[33m"),
# 			)

# 		if "streams=" not in url:
# 			return prefix_for_color

# 		_, streams_part = url.split("streams=", 1)
		
# 		stream_tokens = [tok for tok in streams_part.split("/") if tok]

# 		if len(stream_tokens) < 3:
			
# 			return f"{prefix_for_color}streams=" + "/".join(stream_tokens)

# 		first_token = stream_tokens[0]
# 		last_token = stream_tokens[-1]

# 		return f"{prefix_for_color}streams={first_token}/.../{last_token}"

# 	except Exception as e:

# 		raise RuntimeError(
# 			f"[{my_name()}] Failed to format WebSocket URL: {e}"
# 		) from e

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

	def format(self, record):

		original_levelname = record.levelname
		color = CMAP4TXT.get(original_levelname, '')
		if color:
			record.levelname = f"{color}{original_levelname}{RESET4TXT}"
		
		formatted = super().format(record)

		record.levelname = original_levelname
		return formatted

	def formatTime(self, record, datefmt = None):

		dt = datetime.fromtimestamp(
			record.created,
			tz = timezone.utc,
		)

		if datefmt: return dt.strftime(datefmt)
		
		return (
			dt.strftime("%Y-%m-%d %H:%M:%S.")
			+ f"{dt.microsecond // 1000:03d}Z"
		)

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

		except asyncio.CancelledError:
			
			raise

		except Exception as e:

			try:

				logger = get_subprocess_logger()

			except Exception:

				logger = logging.getLogger()
			
			logger.critical(
				f"{coro_func.__name__} failed: {e}",
				exc_info = True,
			)

			await force_flush_logger(logger)
			
			raise

	wrapper.__name__ = coro_func.__name__
	wrapper.__doc__  = coro_func.__doc__

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