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
import sys, os, time
import random
import shutil
import statistics
import threading
import zipfile
from collections import deque

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

# Set up rotating file handler with UTC timestamps.
# This will create a log file named "stream_binance.log" with rotation.
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

LATENCY_DEQUE_SIZE    = int(CONFIG.get("LATENCY_DEQUE_SIZE", 10))
LATENCY_SAMPLE_MIN    = int(CONFIG.get("LATENCY_SAMPLE_MIN", 10))
LATENCY_THRESHOLD_SEC = float(CONFIG.get("LATENCY_THRESHOLD_SEC", 0.5))

median_latency_dict = {symbol: 0.0 for symbol in SYMBOLS}
depth_update_id_dict = {symbol: 0 for symbol in SYMBOLS}

# ─────────────────────────────────────────────────────────────
# 🕒 Backoff and Order Book Save Configuration
# ─────────────────────────────────────────────────────────────
BASE_BACKOFF		= int(CONFIG.get("BASE_BACKOFF", 2))
MAX_BACKOFF			= int(CONFIG.get("MAX_BACKOFF", 30))
RESET_CYCLE_AFTER   = int(CONFIG.get("RESET_CYCLE_AFTER", 7))
LOB_DIR				= CONFIG.get("LOB_DIR", "./data/binance/orderbook/")
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

# ─────────────────────────────────────────────────────────────
# 🧰 Utility Functions: File Naming and Compression
# ─────────────────────────────────────────────────────────────

def get_file_suffix(interval_min: int, event_ts_ms: int) -> str:
	"""
	Generates a timestamp-based suffix for filenames used in order book persistence.

	The suffix is derived from the snapshot's 'eventTime', which reflects
	the UTC timestamp (in milliseconds) when the snapshot was received by
	the client from the Binance WebSocket stream. This timestamp determines
	the file grouping interval for saving and later zipping.

	Args:
		interval_min (int): File save interval in minutes.
		event_ts_ms (int): Snapshot event time in milliseconds (UTC), from 'eventTime'.

	Returns:
		str: Formatted timestamp string for use in filenames (e.g., '2025-07-01_13-00').
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

def merge_day_zips_to_single_jsonl(
	symbol: str,
	day_str: str,
	base_dir: str,
	purge: bool = True
):
	"""
	Merge all per-minute zipped order book snapshots into a single .jsonl file for the given day,
	then re-compress the result as a single zip archive. Optionally purge temporary files.

	This routine is robust against missing files and concurrent I/O artifacts,
	and is designed for post-processing in long-running systems where partial writes may occur.

	Args:
		symbol (str):
			Trading symbol, e.g., "btcusdt"
		day_str (str):
			Target date in "YYYY-MM-DD" format
		base_dir (str):
			Root path where order book data is stored
		purge (bool):
			If True, deletes the per-minute zipped snapshot folder after merging

	Handled Scenarios:
		- Temporary folder may not exist (e.g., stream failure or date mismatch)
		- Folder may exist but be empty (e.g., early startup with no snapshots)
		- Individual .zip files might be missing or removed mid-process
		- Corrupted zips or concurrent file deletions are caught and logged safely
	"""

	# ── Construct working directories and target paths
	tmp_dir = os.path.join(
		base_dir,
		"temporary",
		f"{symbol.upper()}_orderbook_{day_str}"
	)
	merged_path = os.path.join(
		base_dir,
		f"{symbol.upper()}_orderbook_{day_str}.jsonl"
	)

	# ── 1. Abort early if directory is missing (no data captured for this day)
	if not os.path.isdir(tmp_dir):
		return

	# ── 2. List all zipped minute-level snapshots (may be empty)
	zip_files = [f for f in os.listdir(tmp_dir) if f.endswith(".zip")]
	if not zip_files:
		return

	try:
		# ── 3. Open output file for merged .jsonl content
		with open(merged_path, "w", encoding="utf-8") as fout:
			# ── 4. Process each zip file in chronological order
			for zip_file in sorted(zip_files):
				zip_path = os.path.join(tmp_dir, zip_file)

				# ── 5. Unzip each file and stream its lines directly into the merged file
				with zipfile.ZipFile(zip_path, "r") as zf:
					for member in zf.namelist():
						with zf.open(member) as f:
							for raw in f:
								fout.write(raw.decode("utf-8"))

		# ── 6. Recompress the consolidated .jsonl into a final single-archive zip
		final_zip = merged_path.replace(".jsonl", ".zip")
		with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.write(merged_path, arcname=os.path.basename(merged_path))

		# ── 7. Remove intermediate plain-text .jsonl file after compression
		if os.path.exists(merged_path):
			os.remove(merged_path)

		# ── 8. Optionally delete the original temp folder containing per-minute zips
		if purge:
			shutil.rmtree(tmp_dir)

	except FileNotFoundError as e:
		# ── Likely due to concurrent cleanup (e.g., temp folder or zip deleted externally)
		logger.warning(
			f"[merge_day_zips] No files found to merge for {symbol} on {day_str}: {e}"
		)
		return

	except Exception as e:
		# ── Catch-all safeguard for any other unexpected I/O error
		logger.error(
			f"[merge_day_zips] Unexpected error merging {symbol} on {day_str}: {e}",
			exc_info=True
		)
		return

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

	global save_queue

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

	global median_latency_dict, save_queue
	attempt = 0

	while True:
		await latency_ok.wait()  # Pause if latency quality is insufficient
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

					# Before handling each snapshot, enforce latency quality
					if not latency_ok.is_set() or not latency_dict[symbol]:
						continue  # Skip processing until latency is trusted

					# If passed, we are guaranteed latency_dict has valid samples
					med_latency = int(median_latency_dict.get(symbol, 0.0))
					event_ts = int(time.time() * 1_000) - med_latency

					snapshot = {
						"lastUpdateId": last_update,
						"eventTime": event_ts,
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

async def consume_depth_updates() -> None:

	global median_latency_dict, depth_update_id_dict

	url = (
		"wss://stream.binance.com:9443/stream?"
		+ "streams=" + "/".join(f"{symbol}@depth" for symbol in SYMBOLS)
	)
	
	attempt = 0
	while True:
		try:
			async with websockets.connect(url) as ws:
				logger.info(f"Connected to {url} (@depth)")
				attempt = 0
				# Reset latency tracking state
				async for raw in ws:
					msg = json.loads(raw)
					stream = msg.get("stream", "")
					symbol = stream.split("@", 1)[0].lower()
					if symbol not in SYMBOLS:
						continue

					data = msg.get("data", {})
					update_id = data.get("u")
					if update_id is None:
						continue
					if update_id <= depth_update_id_dict.get(symbol, 0):
						continue
					depth_update_id_dict[symbol] = update_id

					server_time = data.get("E")
					if server_time is None:
						continue
						
					# 2025-07-02 (Stuttgart):
					# Local clock is not synchronized with server time.
					# Tried to fix local clock via NTP tuning.
					# But, `w32tm` shows dispersion ≈ 8s (too high)
					# Local time is not reliable for latency check.
					# Let's just clamp at the moment to improve this
					# part later.

					client_time = time.time()
					latency = max(0.0, client_time - (server_time / 1000))

					if latency < 0:
						logger.warning(
							f"[latency-debug] NEGATIVE: server={server_time}, "
							f"client={client_time}, delta={latency:.3f}s"
						)

					latency_dict[symbol].append(latency)

					# Debugging output for latency tracking
					# Uncomment to log latency for specific symbols
					# if symbol == "btcusdc":
					#	logger.info(f"[latency] {symbol} -> {latency:.1f} ms, samples = {len(latency_dict[symbol])}")

					# Check if enough samples are accumulated to evaluate latency readiness
					if len(latency_dict[symbol]) >= LATENCY_SAMPLE_MIN:
						med_latency = statistics.median(latency_dict[symbol])
						median_latency_dict[symbol] = med_latency	# cache median latency
						if med_latency < LATENCY_THRESHOLD_SEC:		# Threshold: 500 ms
							if not latency_ready_event.is_set():
								latency_ready_event.set()
								logger.info(
									f"[latency] Latency OK — event set (median = {med_latency * 1000:.1f} ms)"
								)
								
		except Exception as e:
			
			attempt += 1
			logger.warning(f"[consume_depth_updates] Connection error (attempt {attempt}): {e}")

			# Reset latency tracking state
			latency_ready_event.clear()
			for symbol in SYMBOLS:
				latency_dict[symbol] = deque(maxlen=LATENCY_DEQUE_SIZE)
				depth_update_id_dict[symbol] = 0

			backoff = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 1)
			if attempt > RESET_CYCLE_AFTER:
				attempt = 3
			logger.warning(
				f"[consume_depth_updates] Retrying in {backoff:.1f} seconds (attempt {attempt})..."
			)
			await asyncio.sleep(backoff)

		finally:
			logger.info("[consume_depth_updates] WebSocket connection closed.")

async def watch_latency_signal() -> None:
	"""
	Monitor latency_ready_event to control latency_ok flag.

	Logic:
	- During initial warm-up, print "[watcher] Warming up latency measurements..."
	- Set latency_ok only if latency_ready_event is set.
	- Clear latency_ok only if:
		• latency_ready_event is not set, and
		• All symbols have at least one latency sample
	"""
	has_logged_warmup = False

	while True:
		is_ready = latency_ready_event.is_set()
		is_ok = latency_ok.is_set()
		has_latency_data = all(len(latency_dict[s]) > 0 for s in SYMBOLS)

		if is_ready and not is_ok:
			logger.info("[watcher] Latency normalized. Resuming order book stream.")
			latency_ok.set()
			has_logged_warmup = False  # Reset

		elif not is_ready:
			if not has_latency_data and not has_logged_warmup:
				logger.info("[watcher] Warming up latency measurements...")
				has_logged_warmup = True

			elif has_latency_data and is_ok:
				logger.warning("[watcher] Latency degraded. Pausing order book stream.")
				latency_ok.clear()

		await asyncio.sleep(0.2)

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

if __name__ == "__main__":

	import asyncio
	from uvicorn.config import Config
	from uvicorn.server import Server

	async def main():

		# Initialize in-memory structures
		global ready_event, save_queue, depth_update_id_dict, median_latency_dict
		global latency_dict, latency_ready_event, latency_ok
		save_queue = asyncio.Queue()
		latency_dict = {symbol: deque(maxlen=LATENCY_DEQUE_SIZE) for symbol in SYMBOLS}
		median_latency_dict = {symbol: 0.0 for symbol in SYMBOLS}
		depth_update_id_dict = {symbol: 0 for symbol in SYMBOLS}
		ready_event = asyncio.Event()
		latency_ready_event = asyncio.Event()
		latency_ok = asyncio.Event()
		latency_ok.clear()

		# Launch background tasks
		asyncio.create_task(orderbook_writer())				# Handles periodic snapshot persistence
		asyncio.create_task(consume_order_books())			# Streams and stores depth20@100ms snapshots
		asyncio.create_task(consume_depth_updates())		# Streams @depth for latency estimation
		asyncio.create_task(watch_latency_signal())  		# Synchronize latency control

		# Wait for at least one valid snapshot before serving
		await ready_event.wait()

		# FastAPI
		logger.info(
			f"FastAPI server starts, e.g., "
			f"<  http://localhost:8000/orderbook/{SYMBOLS[0]}  >"
		)
		cfg = Config(app=app, host="0.0.0.0", port=8000, lifespan="off", use_colors=False)
		server = Server(cfg)
		await server.serve()

	asyncio.run(main())
