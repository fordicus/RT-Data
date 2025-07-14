import os, sys
from pathlib import Path

r"""................................................................................
How to Use:
	Run this script in a local Python environment.
	Provide the target directory as a command-line argument.
	Example: python get_bybit_chart_dom_sizes.py <mother_directory>

Example Output:
   1 ETHUSDT  104: 4.75 GB
   2 BTCUSDT  104: 4.70 GB
   3 SOLUSDT  104: 2.54 GB
   ...
  28 SHIBUSDT 104: 506.12 MB
  29 PEPEUSDC 104: 474.48 MB
  30 BNBUSDT  104: 453.92 MB

Dependency:
	- Requires a valid 'get_bybit_chart_dom.conf' file in the same directory.
	- Assumes data files are stored in the provided 'mother_directory'.

Functionality:
	- Loads SYMBOLS from the config file.
	- Scans target directory for files matching SYMBOLS and patterns.
	- Aggregates count and total file size per symbol.

IO Structure:
	Input:  Config file path, Target directory path
	Output: Printed summary of file count and total size per symbol
................................................................................"""

# Validate command-line arguments
if len(sys.argv) < 2:
	print("Usage: python get_bybit_chart_dom_sizes.py <mother_directory>")
	sys.exit(1)

# Define parent folder path from command-line argument
mother_directory = sys.argv[1]
mother_path = Path(mother_directory)

# Load all entries from the provided directory
all_items = os.listdir(mother_directory)

# Extract only files (exclude folders)
file_names = [f for f in all_items if os.path.isfile(os.path.join(mother_directory, f))]

def load_symbols_manual(conf_path: str) -> list[str]:
	"""Extracts a comma-separated SYMBOLS=... definition from a config file."""
	# Initialize an empty list to store symbols
	symbols = []

	# Open the configuration file and parse its contents
	with open(conf_path, 'r', encoding='utf-8') as f:
		for line in f:
			line = line.strip()

			# Skip empty lines or comments
			if not line or line.startswith('#'):
				continue

			# Find SYMBOLS=... and split by comma
			if line.upper().startswith('SYMBOLS'):
				_, value = line.split('=', 1)
				symbols = [s.strip() for s in value.split(',') if s.strip()]
				break

	return symbols

# Load symbols from the configuration file
symbols = load_symbols_manual('get_bybit_chart_dom.conf')

# Initialize counters for file count and total size per symbol
dict_symbols_cnt  = {sym: 0 for sym in symbols}
dict_symbols_size = {sym: 0 for sym in symbols}

def format_size(bytes_: int) -> str:
	"""Convert byte count into human-readable size."""
	# Iterate through units to find the appropriate size representation
	for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
		if bytes_ < 1024:
			return f"{bytes_:.2f} {unit}"
		bytes_ /= 1024
	return f"{bytes_:.2f} PB"

# Define file patterns for order book and execution chart
ob_ext = 'ob200.data.zip'
ex_ext = '.csv.gz'

# Scan files for each symbol
for s in symbols:
	for f in file_names:
		# Define patterns for matching symbols in filenames
		ob_sym = '_' + s + '_'
		ex_sym = s + '_'

		# Check if the file matches the patterns
		if (
			((ob_sym in f) and (ob_ext in f)) or
			((f.startswith(ex_sym)) and (ex_ext in f))
		):
			# Count matching files for the symbol
			dict_symbols_cnt[s] += 1

			# Get file size from absolute path
			abs_path = mother_path / f
			byte_sz = os.path.getsize(abs_path)

			# Accumulate total byte size for the symbol
			dict_symbols_size[s] += byte_sz

# Sort symbols by descending file size
dict_symbols_size = dict(
	sorted(dict_symbols_size.items(), key=lambda x: x[1], reverse=True)
)

# Print final result
cnt = 1
for sym in dict_symbols_size:
	print(
		f"{cnt:>4} {sym:<8} {dict_symbols_cnt[sym]}: "
		f"{format_size(dict_symbols_size[sym])}"
	)
	cnt += 1
