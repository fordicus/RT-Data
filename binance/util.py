# stream_binance_globals.py

import sys, os, time, inspect, logging
from datetime import datetime, timezone

# ───────────────────────────────────────────────────────────────────────────────

CONFIG_PATH = "get_binance_chart.conf"

# ───────────────────────────────────────────────────────────────────────────────
# Technical Utilities
# ───────────────────────────────────────────────────────────────────────────────

def my_name():
	frame = inspect.stack()[1]
	return f"{frame.function}:{frame.lineno}"

# ───────────────────────────────────────────────────────────────────────────────

def resource_path(	# Resource Resolver for PyInstaller
	relative_path:	str,
	logger:			logging.RootLogger
) -> str:

	try:

		if not isinstance(logger, logging.Logger):

			raise TypeError(
				f"logger must be an instance of "
				f"logging.Logger"
			)

		logger.info(
			f"[{my_name()}] Called with "
			f"relative_path='{relative_path}'"
		)

		base = getattr(sys, "_MEIPASS",
			os.path.dirname(__file__)
		)

		return os.path.join(base, relative_path)

	except Exception as e:

		raise RuntimeError(
			f"[{my_name()}] Failed to "
			f"resolve path: {relative_path}"
		) from e

# ───────────────────────────────────────────────────────────────────────────────
# Time Utilities
# ───────────────────────────────────────────────────────────────────────────────

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

# ───────────────────────────────────────────────────────────────────────────────

def load_config(
	# shared root logger injected
	logger: logging.RootLogger
) -> tuple[
		dict[str, str],
		list[str],
		str
	]:

	def extract_symbols(
		config: dict[str, str]
	) -> list[str]:

		try:

			symbols_str = config.get("SYMBOLS")

			if not isinstance(symbols_str, str):

				raise ValueError(
					f"SYMBOLS field missing "
					f"or not a string"
				)

			return [
				s.lower()
				for s in symbols_str.split(",")
				if s.strip()
			]

		except Exception as e:

			raise RuntimeError(
				f"[{my_name()}] Failed to "
				f"extract symbols from config."
			) from e
		
	try:

		with open(
			resource_path(CONFIG_PATH, logger),
			'r', encoding='utf-8'
		) as f:

			config: dict[str, str] = {}	# loaded from .conf

			for line in f:

				line = line.strip()

				if (
					not line
					or line.startswith("#")
					or "=" not in line
				):
					continue

				line = line.split("#", 1)[0].strip()
				parts = line.split("=", 1)
				if len(parts) != 2:
					continue
				key, val = parts
				config[key.strip()] = val.strip()
		
		SYMBOLS = extract_symbols(config)

		if not SYMBOLS:

			raise RuntimeError(
				f"No SYMBOLS loaded from config."
			)

		WS_URL = (
			f"wss://stream.binance.com:9443/stream?streams="
			f"{'/'.join(f'{sym}@depth20@100ms' for sym in SYMBOLS)}"
		)

		return config, SYMBOLS, WS_URL

	except Exception as e:

		raise RuntimeError(
			f"[{my_name()}] Failed to load config."
		) from e

# ───────────────────────────────────────────────────────────────────────────────
