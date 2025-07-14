#!/usr/bin/env python3
r"""................................................................................
BYBIT CHART + ORDERBOOK VALIDATOR (Python 3.9.19)

▸ Purpose:
  Validate previously downloaded ByBit spot chart (.csv.gz) and DOM snapshot
  (.data.zip) files to ensure data integrity before RL training or analysis.

▸ Usage:
  $ python get_bybit_chart_dom_validated.py

  The script prompts for a folder path containing downloaded files.
  It checks that:
    • The folder exists
    • The number of .csv.gz and .data.zip files match exactly

  Then, it launches parallel validation of all files:
    • Chart files → validated via gzip decoding + header check
    • DOM files   → validated via zip decoding + NDJSON key scan

▸ Features:
  • ✅ 100% coverage validation (not sampling)
  • ✅ Per-file console feedback with index progress
  • ✅ ThreadPoolExecutor-based parallel execution
  • ✅ Graceful failure for decode/malformed errors

▸ File Requirements:
  - Chart: SYMBOL_YYYY-MM-DD.csv.gz
  - DOM  : YYYY-MM-DD_SYMBOL_ob200.data.zip

▸ Dependencies:
  - Python 3.9.19 (standard library only — no third-party packages required)

▸ Notes:
  - The original downloader script is `get_bybit_chart_dom.py`
  - This script is intended for post-download data integrity assurance

................................................................................"""

# ---------------------------------------------------------------------
# PACKAGE IMPORTS
# ---------------------------------------------------------------------

# ⬇️ Standard modules for file system, compression, and parallelism
import os, gzip, zipfile, random

# ⬇️ Pathlib for platform-safe file path manipulation
from pathlib import Path

# ⬇️ Datetime for timestamps and console logging
from datetime import datetime

# ⬇️ Thread pool for concurrent validation jobs
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------------------
# CONFIGURABLE GLOBALS
# ---------------------------------------------------------------------

MAX_WORKERS = 8  # parallel validation threads

# ---------------------------------------------------------------------
# VALIDATION UTILITIES
# ---------------------------------------------------------------------

def validate_csv(path: Path) -> bool:
	"""
	Validate a chart CSV file (.csv.gz format).

	This function decompresses the gzip file, reads all lines,
	and verifies that the header includes required fields.

	✅ Validation Rules:
	- First line must contain a header.
	- Header must include 'time'.
	- Header must also include either 'price' or 'value'.

	Returns:
	- True if valid chart format is detected.
	- False if file is malformed or unreadable.
	"""
	try:
		with gzip.open(path, 'rt', encoding='utf-8') as fin:
			lines = list(fin)
		header = lines[0].lower()
		return 'time' in header and ('price' in header or 'value' in header)
	except Exception as e:
		print(f"[ERROR] {path.name}: {e}")
		return False


def validate_dom(path: Path) -> bool:
	"""
	Validate a DOM snapshot file (.data.zip format).

	This function extracts the first file inside the ZIP archive and
	scans through all lines to verify DOM content.

	✅ Validation Rules:
	- File must contain JSON lines.
	- At least one line must contain either '"a":' or '"b":'.

	Returns:
	- True if a valid DOM line is found.
	- False if file is empty, malformed, or unreadable.
	"""
	try:
		with zipfile.ZipFile(path, 'r') as z:
			names = z.namelist()
			with z.open(names[0]) as d:
				for line in d:
					decoded = line.decode('utf-8')
					if '"a":' in decoded or '"b":' in decoded:
						return True
		return False
	except Exception as e:
		print(f"[ERROR] {path.name}: {e}")
		return False

# ---------------------------------------------------------------------
# WORKER WRAPPER
# ---------------------------------------------------------------------

def validate_file(idx: int, total: int, path: Path) -> bool:
	"""
	Worker wrapper to validate a single file (chart or DOM).

	Determines the file type by suffix:
	- .csv.gz → chart file → validate_csv()
	- .data.zip → DOM file → validate_dom()

	Prints a status message to stdout with flush enabled to ensure
	progress visibility even when run in buffered environments.
	"""
	is_chart = path.suffix == '.gz'
	ok = validate_csv(path) if is_chart else validate_dom(path)

	if ok:
		print(f"[{idx}/{total}] {path.name} successfully validated.", flush=True)
	else:
		print(f"[{idx}/{total}] {path.name} failed to validate.", flush=True)

	return ok

# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

if __name__ == '__main__':
	"""
	Entry point for standalone validation script.
	Prompts user for data folder, collects all .csv.gz and .data.zip files,
	and validates them in parallel using a thread pool.

	Exits early if:
	- folder is not found
	- file counts between chart and DOM are unequal
	"""
	print(f"[{datetime.now()}] Welcome to ByBit Data Validator\n")

	# Prompt user for path to downloaded data files
	dest_input = input("Enter the path to the data folder: ").strip()
	data_dir = Path(dest_input).expanduser().resolve()

	if not data_dir.exists():
		print(f"[ERROR] Folder not found: {data_dir}")
		exit(1)

	# Collect file paths for validation
	chart_files = sorted(data_dir.glob("*.csv.gz"))
	dom_files   = sorted(data_dir.glob("*.data.zip"))

	# File count must match for 1:1 pair validation
	if len(chart_files) != len(dom_files):
		print(f"[ERROR] File count mismatch: {len(chart_files)} chart vs {len(dom_files)} DOM")
		exit(1)

	total = len(chart_files) + len(dom_files)
	all_files = chart_files + dom_files

	print(f"\n[{datetime.now()}] Validating {total} files ({len(chart_files)} pairs)...\n")

	# Launch parallel validation using threads
	with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
		futures = [
			executor.submit(validate_file, idx, total, path)
			for idx, path in enumerate(all_files, 1)
		]
		success = [f.result() for f in futures]

	# Final status report
	ok_count = sum(success)
	print("\n----------------------------------------------")
	if ok_count == total:
		print(f"[{datetime.now()}] ✅ All files successfully validated.")
	else:
		print(f"[{datetime.now()}] ❌ {ok_count}/{total} files passed validation.")
