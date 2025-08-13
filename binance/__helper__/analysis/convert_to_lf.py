r"""
Usage:

	# Batch convert from a list, with backup archive directory
	
		python convert_to_lf.py -batch list.txt -archive C:/Temp/CRLF
	
	# Convert a single file
	
		python convert_to_lf.py "C:\workspace\RT-Data\binance\__helper__\convert_to_lf.py"

Notes:

	- If a file uses CRLF line endings, a backup is saved with '_original' suffix.
	- For batch mode, backup files are stored in the specified archive directory.
	- The batch list must contain one file path per line (absolute or relative).
"""

import sys
import pathlib
import os

def convert_to_lf(filepath: str, archive_dir: str = None):
	path = pathlib.Path(filepath)

	if not path.is_file():
		print(f"Error: File does not exist: {filepath}")
		return

	content = path.read_bytes()

	if b'\r\n' not in content:
		print(f"Already LF: {filepath}")
		return

	# Determine backup path
	if archive_dir:
		archive_path = pathlib.Path(archive_dir)
		archive_path.mkdir(parents=True, exist_ok=True)
		backup_file = archive_path / (path.stem + "_original" + path.suffix)
	else:
		backup_file = path.with_stem(path.stem + "_original")

	# Save backup
	backup_file.write_bytes(content)
	print(f"Backup created: {backup_file}")

	# Convert and overwrite original
	converted = content.replace(b'\r\n', b'\n')
	path.write_bytes(converted)
	print(f"Converted CRLF to LF: {path}")

def main():
	args = sys.argv[1:]

	if not args:
		print("Usage: see script docstring.")
		sys.exit(1)

	if args[0] == "-batch":
		if len(args) < 2:
			print("Error: Missing list file after -batch")
			sys.exit(1)

		list_path = pathlib.Path(args[1])
		if not list_path.is_file():
			print(f"Error: List file does not exist: {list_path}")
			sys.exit(1)

		archive_dir = None
		if "-archive" in args:
			i = args.index("-archive")
			if i + 1 < len(args):
				archive_dir = args[i + 1]
			else:
				print("Error: Missing directory path after -archive")
				sys.exit(1)

		for line in list_path.read_text(encoding='utf-8').splitlines():
			line = line.strip()
			if line:
				convert_to_lf(line, archive_dir)

	else:
		# Single file mode
		if len(args) != 1:
			print("Error: Provide exactly one file path or use -batch mode.")
			sys.exit(1)
		convert_to_lf(args[0])

if __name__ == "__main__":
	main()
