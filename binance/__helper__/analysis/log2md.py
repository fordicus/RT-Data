# log2md.py

#———————————————————————————————————————————————————————————————————————————————
# python log2md.py "C:\workspace\RT-Data\binance\__temp__\stream_binance.log"
#———————————————————————————————————————————————————————————————————————————————

r"""————————————————————————————————————————————————————————————————————————————

python log2md.py "C:\workspace\RT-Data\binance\__temp__\stream_binance.log"

————————————————————————————————————————————————————————————————————————————————

log2md.py — Convert ANSI-colored Linux logs to Markdown (.md)
- Replace ANSI SGR (escape sequences) → <span style="color:...">
- Preserve all spaces/newlines, including two-space at end of line ("  ")
- Wrap the result in <pre>...</pre> to maintain colors/spacing
  in Markdown renderers

Usage:
	python log2md.py /absolute/path/to/your.log
	# Output: /absolute/path/to/your.md

————————————————————————————————————————————————————————————————————————————"""

from __future__ import annotations
import argparse
import html
import re
from pathlib import Path

ESC = "\x1b"
SGR_RE = re.compile(r"\x1b\[((?:\d+;)*\d+)m")

# 256-color (38;5;n) mapping — only frequently used codes are
# mapped exactly (requested spec: 1:1)
PALETTE_256_TO_HEX = {
	242: "#6c6c6c",  # cool gray (approx for 242)
	34:  "#00af00",  # green (approx for 34)
	214: "#ffaf00",  # orange
	196: "#ff0000",  # bright red
	199: "#ff005f",  # magenta red
}

# Basic 8 colors (30–37) → HEX
BASIC_30_37 = {
	30: "#000000",  # black
	31: "#ff0000",  # red
	32: "#00ff00",  # green
	33: "#ffff00",  # yellow
	34: "#0000ff",  # blue
	35: "#ff00ff",  # magenta
	36: "#00ffff",  # cyan
	37: "#ffffff",  # white
}

RESET_CODES = {0}  # SGR reset

def _open_span(color_hex: str) -> str:
	return f'<span style="color:{color_hex}">'

def _close_span() -> str:
	return "</span>"

def _params_to_color_hex(params: list[int]) -> str | None:
	"""
	Supported:
	  - 38;5;N (256-color)  → exact mapping for specified codes only
	  - 38;2;R;G;B (truecolor)
	  - 30–37 (basic 8-color)
	For unsupported codes, color is unchanged (None).
	"""
	if not params:
		return None

	# Truecolor: 38;2;R;G;B
	if len(params) >= 5 and params[0] == 38 and params[1] == 2:
		r, g, b = params[2], params[3], params[4]
		r = max(0, min(255, r))
		g = max(0, min(255, g))
		b = max(0, min(255, b))
		return f"#{r:02x}{g:02x}{b:02x}"

	# 256-color: 38;5;N
	if len(params) >= 3 and params[0] == 38 and params[1] == 5:
		n = params[2]
		if n in PALETTE_256_TO_HEX:
			return PALETTE_256_TO_HEX[n]
		# Unmapped codes: no color applied
		# (only requested mapping range is forced 1:1)
		return None

	# Basic 8 colors: 30–37
	if len(params) == 1 and params[0] in BASIC_30_37:
		return BASIC_30_37[params[0]]

	return None

def ansi_line_to_html(line: str) -> str:
	"""
	Replace ANSI color sequences with HTML <span> tags.
	At the end of each line, close any open spans.
	Escape HTML special characters for safety.
	"""
	out_parts = []
	last = 0
	open_span = False

	for m in SGR_RE.finditer(line):
		# Output normal text before this sequence (HTML escape required)
		segment = line[last:m.start()]
		if segment:
			out_parts.append(html.escape(segment))
		last = m.end()

		# Parse SGR parameters
		params = [int(p) for p in m.group(1).split(";") if p]
		# Reset?
		if any(p in RESET_CODES for p in params):
			if open_span:
				out_parts.append(_close_span())
				open_span = False
			# Reset produces no extra text
			continue

		color_hex = _params_to_color_hex(params)
		if color_hex:
			# Before applying a new color, close the existing span
			if open_span:
				out_parts.append(_close_span())
			out_parts.append(_open_span(color_hex))
			open_span = True
		# Unsupported SGR codes are ignored (no text change)

	# Remaining text after last escape sequence
	tail = line[last:]
	if tail:
		out_parts.append(html.escape(tail))

	# Close open span at end of line
	if open_span:
		out_parts.append(_close_span())
		open_span = False

	return "".join(out_parts)

def convert_file_to_md(input_path: Path) -> Path:
	output_path = input_path.with_suffix(".md")
	with input_path.open("r", encoding="utf-8", errors="replace") as f:
		lines = f.readlines()

	# Wrap in <pre> block to preserve spaces/newlines/two-space at EOL
	html_lines = [ansi_line_to_html(line.rstrip("\n")) for line in lines]
	content = "<pre>\n" + "\n".join(html_lines) + "\n</pre>\n"

	with output_path.open("w", encoding="utf-8", newline="\n") as f:
		f.write(content)

	return output_path

def main():
	ap = argparse.ArgumentParser(
		description = "ANSI-colored log → Markdown(.md) converter"
	)
	ap.add_argument(
		"input", type = str, help = "Absolute path to input log file"
	)
	args = ap.parse_args()
	src = Path(args.input).expanduser().resolve()
	if not src.exists():
		raise FileNotFoundError(f"input not found: {src}")
	dst = convert_file_to_md(src)
	print(f"Saved: {dst}")

if __name__ == "__main__":
	main()
