r"""................................................................................
How to Use:

	python get_binance_chart.py --start-date 2025-06-01 --end-date 2025-06-24

Dependency:
	Python ≥ 3.9.19
	curl (available in PATH)

Functionality:
	This script downloads daily Binance SPOT aggTrades files as .zip archives.
	It verifies file integrity using Binance-provided .CHECKSUM and SHA256 hash,
	without unpacking the archive. All downloads are run in parallel with a
	ThreadPoolExecutor and integrity check is atomic.

IO Structure:
	- Input: 
		--start-date, --end-date via CLI
		app.conf file with keys: SYMBOLS, MAX_WORKERS, TIMEOUT
	- Output: 
		.zip files saved in ./downloads/<symbol>/ 
		Only verified files are retained

Data Field Definitions (within CSV files):
	A. Aggregate tradeId
	B. Price
	C. Quantity
	D. First tradeId
	E. Last tradeId
	F. Timestamp
	G. Was the buyer the maker
	H. Was the trade the best price match

BOLT Scope:
	Only the following fields are used for downstream post-processing:
		- B. Price
		- C. Quantity
		- F. Timestamp
		- G. Was the buyer the maker

Notes:
	- From 2025-01-01 onward, timestamps are in microseconds (µs); earlier are in
	  milliseconds (ms). All timestamps are UTC-based Unix format.
	- The same data can be explored interactively via web:
	  https://data.binance.vision/?prefix=data/spot/daily/aggTrades/BTCUSDT/
	- Checksum validation is done directly on .zip files using hashlib, 
	  without decompression.

Reference:
	https://github.com/binance/binance-public-data
................................................................................"""

"""................................................................................
Import Standard & External Modules
................................................................................"""

# Core OS-level path, exit control, and process management
import os
import sys
import subprocess

# Argument parsing from CLI (--start-date, --end-date)
import argparse

# Cryptographic checksum utility for SHA256 verification
import hashlib

# Date arithmetic (range of daily data)
import datetime

# Thread-safe counter for download progress tracking
import threading

# Thread-based parallel execution for I/O-bound workloads
from concurrent.futures import ThreadPoolExecutor, as_completed

"""................................................................................
Load Configuration and Setup Globals
................................................................................"""

# Path to user-defined configuration file
CONFIG_PATH = "app.conf"
CONFIG = {}

def load_config(conf_path: str):
	try:
		with open(conf_path, 'r', encoding='utf-8') as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#") or "=" not in line:
					continue
				line = line.split("#", 1)[0].strip()
				if "=" in line:
					key, val = line.split("=", 1)
					CONFIG[key.strip()] = val.strip()
	except Exception as e:
		print(f"Failed to load config from {conf_path}: {e}")

load_config(CONFIG_PATH)

SYMBOLS = CONFIG["SYMBOLS"].split(",")
MAX_WORKERS = int(CONFIG.get("MAX_WORKERS", 8))
TIMEOUT = int(CONFIG.get("TIMEOUT", 300))
if "CHART_DIR" not in CONFIG:
	print("Error: Required key 'CHART_DIR' not found in config file.")
	sys.exit(1)

DOWNLOAD_DIR = CONFIG["CHART_DIR"]

"""................................................................................
Static URLs and Runtime State Variables
................................................................................"""

# Binance base endpoint for daily ZIP+CHECKSUM downloads (aggTrades only)
BASE_URL = "https://data.binance.vision/data/spot/daily/aggTrades"

# Global counters for progress reporting (used in multithreaded context)
lock = threading.Lock()
ok_count = 0
total_count = 0		# Dynamically set later after task expansion


"""................................................................................
URL Builder for .zip and .CHECKSUM
................................................................................"""

def build_url(symbol, date):
	"""
	Constructs download URLs and output filename for a given (symbol, date).

	Returns:
		(zip_url, checksum_url, filename)
	"""
	base_name = f"{symbol}-aggTrades-{date}.zip"
	return (
		f"{BASE_URL}/{symbol}/{base_name}",
		f"{BASE_URL}/{symbol}/{base_name}.CHECKSUM",
		base_name
	)

"""................................................................................
Downloader, Checksum Generator, and Verifier
................................................................................"""

def download_with_curl(url, out_path):
	"""
	Downloads a file from URL using curl with timeout and silent mode.
	Returns True if download succeeds, False otherwise.
	"""
	try:
		result = subprocess.run(
			[
				"curl",
				"-L",					# Follow redirects
				"--fail",				# Fail on HTTP errors (4xx, 5xx)
				"--max-time", str(TIMEOUT),
				"-o", out_path, url
			],
			stdout=subprocess.DEVNULL,	# Suppress stdout
			stderr=subprocess.DEVNULL	# Suppress stderr
		)
		return result.returncode == 0
	except Exception:
		return False


def compute_sha256(file_path):
	"""
	Computes SHA256 hash for a given binary file.
	Returns the hex digest string.
	"""
	hash = hashlib.sha256()
	with open(file_path, 'rb') as f:
		for chunk in iter(lambda: f.read(8192), b""):
			hash.update(chunk)
	return hash.hexdigest()


def verify_checksum(zip_path, checksum_path):
	"""
	Verifies file integrity using Binance-provided .CHECKSUM file.

	Returns:
		True if SHA256 matches and filename matches.
		False otherwise.
	"""
	try:
		with open(checksum_path, 'r') as f:
			expected_hash, filename = f.read().strip().split()

		# Ensure filename in .CHECKSUM matches actual .zip name
		if os.path.basename(zip_path) != filename:
			return False

		actual_hash = compute_sha256(zip_path)
		return actual_hash == expected_hash

	except Exception:
		return False

"""................................................................................
Single File Download Routine + Argument Parser
................................................................................"""

def download_task(symbol, date):
	"""
	Handles the full download and verification process for a given symbol-date.

	Steps:
		1. Build .zip and .CHECKSUM URLs
		2. Skip if already downloaded
		3. Download .zip and .CHECKSUM via curl
		4. Verify SHA256 checksum
		5. Increment success counter under thread lock

	Returns:
		True if the file passes checksum and is kept
		False if download or verification fails
	"""
	global ok_count

	url, chk_url, filename = build_url(symbol, date)
	out_dir = DOWNLOAD_DIR
	os.makedirs(out_dir, exist_ok=True)

	zip_path = os.path.join(out_dir, filename)
	chk_path = zip_path + ".CHECKSUM"

	# Skip if the .zip file already exists
	if os.path.exists(zip_path):
		print(f"[=] Skipped (exists): {zip_path}")
		return True

	# Download .zip file
	if not download_with_curl(url, zip_path):
		print(f"[✗] Failed to download: {url}")
		return False

	# Download corresponding .CHECKSUM file
	if not download_with_curl(chk_url, chk_path):
		print(f"[✗] Failed to fetch CHECKSUM: {chk_url}")
		os.remove(zip_path)
		return False

	# Verify .zip file using .CHECKSUM
	if verify_checksum(zip_path, chk_path):
		os.remove(chk_path)
		with lock:
			ok_count += 1
			print(f"[OK {ok_count}/{total_count}] Downloaded: {url}")
		return True
	else:
		os.remove(zip_path)
		print(f"[✗] Invalid file deleted: {zip_path}")
		return False


def parse_args():
	"""
	Parses required CLI arguments:
		--start-date (format: YYYY-MM-DD)
		--end-date   (format: YYYY-MM-DD)

	Returns:
		Namespace with parsed date strings
	"""
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--start-date",
		required=True,
		help="Start date (YYYY-MM-DD)"
	)
	parser.add_argument(
		"--end-date",
		required=True,
		help="End date (YYYY-MM-DD)"
	)
	return parser.parse_args()

"""................................................................................
Main Execution: Task Expansion and Concurrent Download
................................................................................"""

if __name__ == "__main__":
	# Parse command-line date range (inclusive)
	args = parse_args()
	start = datetime.date.fromisoformat(args.start_date)
	end = datetime.date.fromisoformat(args.end_date)

	# Build (symbol, date) tasks for the entire range
	tasks = []
	for i in range((end - start).days + 1):
		date = start + datetime.timedelta(days=i)
		for symbol in SYMBOLS:
			tasks.append((symbol, date.isoformat()))

	# Total task count for progress bar and success ratio
	total_count = len(tasks)

	# Run downloads concurrently using thread pool
	with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
		futures = [
			executor.submit(download_task, symbol, date)
			for symbol, date in tasks
		]
		for _ in as_completed(futures):
			pass	# progress handled inside download_task()

	# Final completion message
	if ok_count == total_count:
		print(f"\n[✔] All {total_count} files downloaded and verified.")
	else:
		print(f"\n[!] Only {ok_count}/{total_count} files downloaded successfully.")
