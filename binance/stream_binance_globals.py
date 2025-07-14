# stream_binance_globals.py

import sys, os, inspect, logging

# ───────────────────────────────────────────────────────────────────────────────

CONFIG_PATH = "get_binance_chart.conf"

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
