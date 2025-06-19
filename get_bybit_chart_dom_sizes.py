import os
from pathlib import Path

r"""................................................................................
How to Use:
	Run this script in a local Python environment after updating the path and conf.

Dependency:
	- Requires a valid 'get_bybit_chart_dom.conf' file in the same directory.
	- Assumes data files are stored in a known 'mother_directory'.

Functionality:
	- Loads SYMBOLS from the config file.
	- Scans target directory for files matching SYMBOLS and patterns.
	- Aggregates count and total file size per symbol.

IO Structure:
	Input:  Config file path, Target directory path
	Output: Printed summary of file count and total size per symbol
................................................................................"""

# Define parent folder path and load all entries
mother_directory = r'C:\workspace\RT-Data\data\from_2025-05-10_to_2025-06-17'
mother_path = Path(mother_directory)
all_items = os.listdir(mother_directory)

# Extract only files (exclude folders)
file_names = [f for f in all_items if os.path.isfile(os.path.join(mother_directory, f))]

def load_symbols_manual(conf_path: str) -> list[str]:
	"""Extracts a comma-separated SYMBOLS=... definition from a config file."""
	symbols = []

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

symbols = load_symbols_manual('get_bybit_chart_dom.conf')

# Initialize counters
dict_symbols_cnt  = {sym: 0 for sym in symbols}
dict_symbols_size = {sym: 0 for sym in symbols}


def format_size(bytes_: int) -> str:
	"""Convert byte count into human-readable size."""
	for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
		if bytes_ < 1024:
			return f"{bytes_:.2f} {unit}"
		bytes_ /= 1024
	return f"{bytes_:.2f} PB"


# Define file patterns
ob_ext = 'ob200.data.zip'	# order book pattern
ex_ext = '.csv.gz'			# execution chart pattern

# Scan files for each symbol
for s in symbols:

	for f in file_names:

		ob_sym = '_' + s + '_'
		ex_sym = s + '_'

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


# Sort by descending file size
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
