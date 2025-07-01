# stream_binance.py

r"""................................................................................

How to Use:

	🧪 Development Mode (e.g., Windows, debugging):
	$ python stream_binance.py

	🐧 Production Mode (Ubuntu, self-contained executable):
	$ ./stream_binance

Note:
	- The production binary is built via `compile_linux.bat`, which uses Docker
	  to produce a statically linked Linux executable from `stream_binance.py`.
	- No Python environment is required at runtime for the production build.

Temporary Simple Order Book Rendering:
		http://localhost:8000/orderbook/btcusdc

................................................................................

Dependency:
	Python ≥ 3.9
	websockets==11.0.3
	fastapi==0.111.0
	uvicorn==0.30.1
	jinja2==3.1.3

Functionality:
	Stream Binance depth20 order books (100ms interval) via combined websocket.
	Maintain top-20 in-memory snapshots for each symbol.
	Periodically persist snapshots to JSONL → zip → aggregate daily.
	Serve REST endpoints for JSON/HTML access and health monitoring.

IO Structure:
	Config:
		- get_binance_chart.conf
			• Shared between `stream_binance.py` and `get_binance_chart.py`
			• Defines symbols, backoff intervals, output paths, etc.
	Inputs:
		- Binance websocket:
		  wss://stream.binance.com:9443/stream?streams={symbol}@depth20@100ms
	Outputs:
		- Zipped JSONL files (per-symbol, per-minute/day):
		  ./data/binance/orderbook/temporary/{symbol}_orderbook_{YYYY-MM-DD}/
		- Daily merged archive:
		  ./data/binance/orderbook/{symbol}_orderbook_{YYYY-MM-DD}.zip
		- API Endpoints:
			/health/live		→ liveness probe
			/health/ready		→ readiness after first snapshot
			/state/{symbol}		→ JSON: current top-20 snapshot
			/orderbook/{symbol}	→ HTML: real-time bid/ask viewer
			
................................................................................

Binance Official GitHub Manual:
	https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md

................................................................................
"""

# ─────────────────────────────────────────────────────────────
# 📦 Built-in Standard Library Imports (Alphabetically Ordered)
# ─────────────────────────────────────────────────────────────
import asyncio
import json
import os
import random
import shutil
import sys
import threading
import time
import zipfile

# ─── Set up rotating log to file + console with UTC timestamps
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

class UTCFormatter(logging.Formatter):
	def formatTime(self, record, datefmt=None):
		dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
		if datefmt:
			return dt.strftime(datefmt)
		return dt.isoformat()
		
log_formatter = UTCFormatter("[%(asctime)s] %(levelname)s: %(message)s")

file_handler = RotatingFileHandler("stream_binance.log", maxBytes=10_000_000, backupCount=3)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ─────────────────────────────────────────────────────────────
# 📦 Third-Party Dependencies (from requirements.txt)
# ─────────────────────────────────────────────────────────────

# 📡 CORE ──────────────────────────────────────────────────────
# websockets:
#   - Core dependency for Binance L2 stream (`depth20@100ms`)
#   - Absolutely required for order book ingestion
import websockets

# 🌐 OPTIONAL (UI/API Layer) ───────────────────────────────────
# fastapi:
#   - Lightweight ASGI framework for dev/debugging
#   - Enables HTTP API (`/state/{symbol}`) + healthchecks
# jinja2 (via FastAPI templates):
#   - Renders HTML order book UI (`/orderbook/{symbol}`)
# ⚠️ These can be removed for headless batch processing
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# ─────────────────────────────────────────────────────────────
# 📁 Utility: PyInstaller-Compatible Resource Resolver
# ─────────────────────────────────────────────────────────────
def resource_path(relative_path: str) -> str:
	"""
	Resolve an absolute path to a file or folder, supporting both:

	  • Development mode (direct script execution)
	  • PyInstaller frozen mode (e.g., self-contained Linux binary)

	PyInstaller bundles all files into a temp directory at runtime.
	This directory is exposed via the _MEIPASS attribute on sys.

	Args:
		relative_path (str):
			Path relative to this script (e.g., "templates/", "config.ini")

	Returns:
		str:
			Absolute filesystem path usable in both dev and bundled modes.
	"""
	base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
	return os.path.join(base, relative_path)

# ───────────────────────────────
# ⚙️ FastAPI App + Template Setup
# ───────────────────────────────
app			= FastAPI()
templates	= Jinja2Templates(directory=resource_path("templates"))

# ───────────────────────────────
# ⚙️ Configuration from .conf
# ───────────────────────────────
# Shared configuration file between `stream_binance.py` and
# `get_binance_chart.py`. Defines key runtime parameters such as
# SYMBOLS, output directory, and backoff strategy.
CONFIG_PATH = "get_binance_chart.conf"
CONFIG = {}  # Dictionary to store parsed key-value pairs

def load_config(conf_path: str):
	"""
	Parses a simple .conf file with `KEY=VALUE` pairs,
	ignoring comments and blanks.
	Populates the global CONFIG dictionary.

	Args:
		conf_path (str): Relative path to configuration file
	"""
	try:
		with open(conf_path, 'r', encoding='utf-8') as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue  # Skip blank/comment lines
				line = line.split("#", 1)[0].strip()  # Remove inline comments
				if "=" in line:
					key, val = line.split("=", 1)
					CONFIG[key.strip()] = val.strip()
	except Exception as e:
		logger.error(f"Failed to load config from {conf_path}: {e}")

# 🔧 Load configuration during module import
load_config(resource_path(CONFIG_PATH))

# ─────────────────────────────────────────────────────────────
# 📊 Stream Parameters Derived from Config
# ─────────────────────────────────────────────────────────────
SYMBOLS = [s.lower() for s in CONFIG.get("SYMBOLS", "").split(",") if s.strip()]
if not SYMBOLS:
	raise RuntimeError("No SYMBOLS loaded from config.")

STREAMS_PARAM = "/".join(f"{sym}@depth20@100ms" for sym in SYMBOLS)
WS_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS_PARAM}"

# ─────────────────────────────────────────────────────────────
# 🕒 Backoff and Order Book Save Configuration
# ─────────────────────────────────────────────────────────────
BASE_BACKOFF		= int(CONFIG.get("BASE_BACKOFF", 2))
MAX_BACKOFF		 = int(CONFIG.get("MAX_BACKOFF", 30))
RESET_CYCLE_AFTER   = int(CONFIG.get("RESET_CYCLE_AFTER", 7))
LOB_DIR			 = CONFIG.get("LOB_DIR", "./data/binance/orderbook/")
SAVE_INTERVAL_MIN   = int(CONFIG.get("SAVE_INTERVAL_MIN", 1440))
PURGE_ON_DATE_CHANGE= int(CONFIG.get("PURGE_ON_DATE_CHANGE", 1))

if SAVE_INTERVAL_MIN > 1440:
	raise ValueError("SAVE_INTERVAL_MIN must be ≤ 1440")

# 📁 Ensure order book directory exists
os.makedirs(LOB_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 📦 Runtime In-Memory Order Book Buffer and Async Primitives
# ─────────────────────────────────────────────────────────────
book_state: dict[str, dict] = {}
#   └── book_state[symbol]: L2 order book snapshot (bids/asks/lastUpdateId)

file_handles: dict[str, tuple[str, asyncio.StreamWriter]] = {}
#   └── file_handles[symbol]: (file_suffix, active file writer handle)

save_queue = asyncio.Queue()
#   └── queue of (symbol, order book data) tuples for batch persistence

ready_event = asyncio.Event()
#   └── used to signal readiness of initial WebSocket setup

# ─────────────────────────────────────────────────────────────
# 🧰 Utility Functions: File Naming and Compression
# ─────────────────────────────────────────────────────────────

def get_file_suffix(interval_min: int, event_ts_ms: int) -> str:
	"""
	Returns a string suffix for the file, based on event timestamp and interval.

	Args:
		interval_min (int): Save interval in minutes.
		event_ts_ms (int): Event time in milliseconds (UTC).

	Returns:
		str: Timestamp string used for zip file grouping.
	"""
	ts = datetime.utcfromtimestamp(event_ts_ms / 1000)
	if interval_min >= 1440:
		return ts.strftime("%Y-%m-%d")
	else:
		return ts.strftime("%Y-%m-%d_%H-%M")

def get_date_from_suffix(suffix: str) -> str:
	"""
	Extracts the date portion from a file suffix.

	Args:
		suffix (str): Filename suffix such as '2025-06-27_13-15'

	Returns:
		str: Date string in 'YYYY-MM-DD'
	"""
	return suffix.split("_")[0]

def zip_and_remove(src_path: str):
	"""
	Zips the specified .jsonl file and removes the original.

	Args:
		src_path (str): Path to the JSONL file to compress
	"""
	if os.path.exists(src_path):
		zip_path = src_path.replace(".jsonl", ".zip")
		with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.write(src_path, arcname=os.path.basename(src_path))
		os.remove(src_path)

def merge_day_zips_to_single_jsonl(symbol: str, day_str: str, base_dir: str, purge: bool = True):
	"""
	Merges multiple zipped .jsonl files for a specific trading day and symbol into a single .jsonl,
	then compresses the result into one .zip file. Optionally purges intermediate files.

	Args:
		symbol (str): Trading pair (e.g., 'btcusdt')
		day_str (str): Date string in 'YYYY-MM-DD' format
		base_dir (str): Base directory for orderbook data
		purge (bool): If True, deletes temporary input directory after merging

	Structure:
		Assumes source .zip files are under:
			base_dir/temporary/{SYMBOL}_orderbook_{YYYY-MM-DD}/
		Final merged archive appears at:
			base_dir/{SYMBOL}_orderbook_{YYYY-MM-DD}.zip
	"""
	tmp_dir	 = os.path.join(base_dir, "temporary", f"{symbol.upper()}_orderbook_{day_str}")
	merged_path = os.path.join(base_dir, f"{symbol.upper()}_orderbook_{day_str}.jsonl")

	if not os.path.isdir(tmp_dir):
		return  # nothing to merge

	with open(merged_path, "w", encoding="utf-8") as fout:
		for zip_file in sorted(os.listdir(tmp_dir)):
			if not zip_file.endswith(".zip"):
				continue
			zip_path = os.path.join(tmp_dir, zip_file)
			with zipfile.ZipFile(zip_path, "r") as zf:
				for name in zf.namelist():
					with zf.open(name) as f:
						for line in f:
							fout.write(line.decode("utf-8"))

	# Recompress into final .zip and optionally remove intermediate files
	final_zip = merged_path.replace(".jsonl", ".zip")
	with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
		zf.write(merged_path, arcname=os.path.basename(merged_path))
	os.remove(merged_path)

	if purge:
		shutil.rmtree(tmp_dir)

def merge_all_symbols_for_day(symbols: list[str], day_str: str):
	"""
	Batch merge: For each symbol, invoke merging logic for zipped intraday snapshots.

	Args:
		symbols (list[str]): List of trading symbols (lowercase)
		day_str (str): Target day (YYYY-MM-DD) to consolidate

	Notes:
		- purge flag is toggled globally via PURGE_ON_DATE_CHANGE setting (0 or 1)
		- Merges are independent across symbols
	"""
	for symbol in symbols:
		merge_day_zips_to_single_jsonl(
			symbol,
			day_str,
			LOB_DIR,
			purge=(PURGE_ON_DATE_CHANGE == 1)
		)

# ───────────────────────────────
# 📝 Background Task: Save to File
# ───────────────────────────────
async def orderbook_writer():
	"""
	Asynchronous background writer loop:
	Consumes (symbol, snapshot) tuples from the save_queue,
	saves them into date/interval-partitioned `.jsonl` files,
	and performs zip + cleanup + merge operations when the day changes.

	Behavior:
	- Saves each snapshot into a file named: {SYMBOL}_orderbook_{SUFFIX}.jsonl
	- One file per symbol and SAVE_INTERVAL_MIN
	- Files reside under: ./data/binance/orderbook/temporary/{SYMBOL}_orderbook_{YYYY-MM-DD}/
	- On date change, triggers merge + compression for the previous day's data

	Note:
	- This function is intended to be started via `asyncio.create_task(orderbook_writer())`
	- Uses in-memory handle tracking (file_handles) to keep appends open per symbol
	"""
	while True:
		symbol, snapshot = await save_queue.get()

		# ── Determine filename suffix (by interval) and date string
		# consume_order_books() → await save_queue.put((symbol, snapshot))
		# orderbook_writer() → symbol, snapshot = await save_queue.get()
		event_ts_ms = snapshot.get("eventTime", int(time.time() * 1000))
		suffix	 = get_file_suffix(SAVE_INTERVAL_MIN, event_ts_ms)
		day_str  = get_date_from_suffix(suffix)
		
		filename = f"{symbol.upper()}_orderbook_{suffix}.jsonl"

		# ── Ensure intermediate directory exists
		tmp_dir   = os.path.join(LOB_DIR, "temporary", f"{symbol.upper()}_orderbook_{day_str}")
		os.makedirs(tmp_dir, exist_ok=True)
		file_path = os.path.join(tmp_dir, filename)

		# ── Lookup or create write handle
		last_suffix, writer = file_handles.get(symbol, (None, None))

		# ── If the day rolled over: spawn async merge+compress of previous day
		if last_suffix and get_date_from_suffix(last_suffix) != day_str:
			threading.Thread(
				target=merge_all_symbols_for_day,
				args=(SYMBOLS, get_date_from_suffix(last_suffix))
			).start()

		# ── If suffix (time window) changed: rotate file writer
		if last_suffix != suffix:
			if writer:
				writer.close()
				zip_and_remove(os.path.join(tmp_dir, f"{symbol.upper()}_orderbook_{last_suffix}.jsonl"))
			writer = open(file_path, "a", encoding="utf-8")
			file_handles[symbol] = (suffix, writer)

		# ── Append snapshot JSON line
		line = json.dumps(snapshot, separators=(",", ":"))
		writer.write(line + "\n")
		writer.flush()

# ───────────────────────────────
# 🔁 WebSocket Consumer with Retry
# ───────────────────────────────
async def consume_order_books() -> None:
	attempt = 0
	while True:
		try:
			async with websockets.connect(WS_URL) as ws:
				logger.info(f"Connected to {WS_URL} (depth20@100ms)")
				attempt = 0

				async for raw in ws:
					msg = json.loads(raw)
					stream = msg.get("stream", "")
					symbol = stream.split("@", 1)[0].lower()
					if symbol not in SYMBOLS:
						continue

					data = msg.get("data", {})
					last_update = data.get("lastUpdateId")
					if last_update is None:
						continue

					bids = data.get("bids", [])
					asks = data.get("asks", [])

					"""
						Partial depth streams like @depth20@100ms do not include
						a server-side event timestamp ("E" field), unlike diff depth
						streams (@depth). This limitation means all timestamping must
						rely on client-side receipt time, which may introduce small
						inconsistencies during interval-based snapshot grouping. We
						accept this trade-off for faster development, but a future
						migration to full diff streams could be considered for more
						precise time alignment. Reference:
							https://tinyurl.com/partial-depth-missing-E
					"""
					snapshot = {
						"lastUpdateId": last_update,
						"eventTime": int(time.time() * 1_000),
						"bids": [[float(p), float(q)] for p, q in bids],
						"asks": [[float(p), float(q)] for p, q in asks],
					}
					book_state[symbol] = snapshot
					await save_queue.put((symbol, snapshot))
					# consume_order_books() → await save_queue.put((symbol, snapshot))
					# orderbook_writer() → symbol, snapshot = await save_queue.get()

					if not ready_event.is_set():
						ready_event.set()

		except Exception as e:
			attempt += 1
			logger.warning(f"WebSocket error (attempt {attempt}): {e}")
			backoff = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 1)
			if attempt > RESET_CYCLE_AFTER:
				attempt = 3
			logger.warning(f"Retrying in {backoff:.1f} seconds...")
			await asyncio.sleep(backoff)

		finally:
			logger.info("WebSocket connection closed.")

# ───────────────────────────────
# 🚀 Startup Hook
# ───────────────────────────────
@app.on_event("startup")
async def startup_event():
	"""
	Triggered when the FastAPI app starts.

	- Launches two background coroutines:
		1. `orderbook_writer`: flushes `save_queue` to disk.
		2. `consume_order_books`: connects to Binance WebSocket and streams orderbook data.
	- Waits for the first `ready_event` to ensure at least one snapshot was received before serving.
	"""
	asyncio.create_task(orderbook_writer())	   # Background task for saving orderbook data to disk
	asyncio.create_task(consume_order_books())	# Binance WebSocket consumer (depth20@100ms)
	await ready_event.wait()					  # Block until at least one valid snapshot arrives
	logger.info(f"Ready. Try <  http://localhost:8000/orderbook/{SYMBOLS[0]}  >")  # Startup banner

# ───────────────────────────────
# 🔍 Healthcheck Endpoints
# ───────────────────────────────

@app.get("/health/live")
async def health_live():
	"""
	Liveness probe — Returns 200 OK unconditionally.
	Used to check if the server process is alive (not necessarily functional).
	"""
	return {"status": "alive"}

@app.get("/health/ready")
async def health_ready():
	"""
	Readiness probe — Returns 200 OK only after first market snapshot is received.

	Before readiness:
		- Server may be running, but not yet connected to Binance stream.
		- Kubernetes/monitoring agents can use this to delay traffic routing.
	"""
	if ready_event.is_set():
		return {"status": "ready"}
	raise HTTPException(status_code=503, detail="not ready")

# ───────────────────────────────
# 🧠 JSON API for Order Book
# ───────────────────────────────

@app.get("/state/{symbol}")
async def get_order_book(symbol: str):
	"""
	Returns the most recent full order book snapshot (depth20) for a given symbol.

	Args:
		symbol (str): Trading pair symbol (e.g., "btcusdt").

	Returns:
		JSONResponse: Snapshot containing lastUpdateId, eventTime, bids, and asks.

	Raises:
		HTTPException 404 if the requested symbol is not being tracked.
	"""
	symbol = symbol.lower()
	if symbol not in book_state:
		raise HTTPException(status_code=404, detail="symbol not found")
	return JSONResponse(content=book_state[symbol])

# ───────────────────────────────
# 👁️ HTML UI for Order Book
# ───────────────────────────────
@app.get("/orderbook/{symbol}", response_class=HTMLResponse)
async def orderbook_ui(request: Request, symbol: str):
	"""
	Renders a lightweight HTML page showing the current order book snapshot for the given symbol.

	Args:
		request (Request): FastAPI request context (used for templating).
		symbol (str): Trading pair symbol (e.g., "btcusdt").

	Returns:
		Jinja2-rendered HTMLResponse of `orderbook.html` with top 20 bids and asks.

	Raises:
		HTTPException 404 if the requested symbol is not available in memory.
	"""
	sym = symbol.lower()
	if sym not in book_state:
		raise HTTPException(status_code=404, detail="symbol not found")

	data = book_state[sym]
	bids = data["bids"]
	asks = data["asks"]
	max_len = max(len(bids), len(asks))  # For consistent rendering in the template

	return templates.TemplateResponse(
		"orderbook.html",
		{
			"request": request,
			"symbol": sym,
			"bids": bids,
			"asks": asks,
			"max_len": max_len,
		},
	)

# ───────────────────────────────
# 🧪 Script Entrypoint (dev + prod-safe)
# ───────────────────────────────
if __name__ == "__main__":
	import uvicorn
	import asyncio
	import sys

	"""
	Universal entrypoint for:
	  - 🧪 Windows development mode: uses uvicorn.run("module:app") to avoid event loop conflicts
	  - 🐧 Linux or PyInstaller-built binary: uses uvicorn.run(app), as previously verified stable
	"""

	is_windows = sys.platform.startswith("win")
	is_frozen = getattr(sys, "frozen", False)  # True if running as PyInstaller binary

	if is_windows and not is_frozen:
		# 💻 Windows dev mode — use module path to prevent event loop issues
		uvicorn.run(
			"stream_binance:app",
			host="0.0.0.0",
			port=8000,
			reload=False,
			use_colors=False
		)
	else:
		# 🐧 Linux or frozen executable — use direct app reference (stable and verified)
		uvicorn.run(
			app,
			host="0.0.0.0",
			port=8000,
			use_colors=False
		)
