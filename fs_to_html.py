r"""................................................................................

How to Use:

	python fs_to_html.py

................................................................................

Dependency:

	pip install gitignore-parser==0.1.12

................................................................................"""

from pathlib import Path
from gitignore_parser import parse_gitignore

# Fallback ignore list in case fs_to_html.ignore is not provided
FALLBACK_IGNORED = {
	".git", "__pycache__", ".idea", ".DS_Store",
	".venv", ".pytest_cache"
}

# Name of optional ignore file that follows .gitignore syntax
IGNORE_FILE = "fs_to_html.ignore"

def load_ignore_func(base: Path):
	"""
	Return a function that determines whether a given path should be ignored.

	Looks for a file named 'fs_to_html.ignore' in the provided base path.
	If found, uses `parse_gitignore` to build the ignore rule.
	Otherwise, uses a fallback set of common ignored patterns.
	"""
	ignore_path = base / IGNORE_FILE

	if ignore_path.exists():
		# Use gitignore-style parsing
		return parse_gitignore(ignore_path)
	else:
		# Fallback: ignore files/folders listed in FALLBACK_IGNORED
		return lambda p: p.name in FALLBACK_IGNORED

def build_html(path: Path, should_ignore, depth: int = 0) -> str:
	"""
	Recursively generate nested HTML from the given path.

	Args:
		path (Path): The file or directory to process.
		should_ignore (Callable): A function to check if a path should be ignored.
		depth (int): Current depth for indentation and nesting.

	Returns:
		str: HTML string representing the directory structure.
	"""
	indent = "  " * depth
	name   = path.name

	# Skip ignored files or folders
	if should_ignore(path):
		return ""

	if path.is_dir():
		# Directory: create a collapsible <details> block
		children = sorted(
			path.iterdir(),
			key = lambda p: (not p.is_dir(), p.name.lower())
		)

		html = f'{indent}<details><summary>📁 {name}/</summary>\n'

		for child in children:
			html += build_html(child, should_ignore, depth + 1)

		html += f'{indent}</details>\n'

	else:
		# File: simple div with icon
		html = f'{indent}<div class="file">📄 {name}</div>\n'

	return html

def full_html_template(title: str, body: str) -> str:
	"""
	Wrap the directory HTML tree in a full HTML5 template.

	Args:
		title (str): Title of the directory being visualized.
		body (str): HTML body content (the tree structure).

	Returns:
		str: A complete HTML document as a string.
	"""
	return f"""<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<title>{title} — Directory Tree</title>
	<style>
		body {{
			font-family: monospace;
			padding: 1rem;
		}}
		details summary {{
			cursor: pointer;
			font-weight: bold;
		}}
		details {{
			margin-left: 1em;
		}}
		.file {{
			margin-left: 1.5em;
			padding: 0.2em 0;
		}}
	</style>
</head>
<body>
<h2>📁 {title}/</h2>
{body}
</body>
</html>
"""

if __name__ == "__main__":
	# Get the current script directory
	root = Path(__file__).parent.resolve()

	# Load ignore rules (from file or fallback)
	should_ignore = load_ignore_func(root)

	# List children sorted by folder first, then filename
	children = sorted(
		root.iterdir(),
		key = lambda p: (not p.is_dir(), p.name.lower())
	)

	# Recursively generate the directory structure in HTML
	tree_html = ''.join(
		build_html(child, should_ignore, 0) for child in children
	)

	# Compose final HTML page
	page = full_html_template(root.name, tree_html)

	# Write the result to an output HTML file
	with open("REPO_STRUCT.html", "w", encoding="utf-8") as f:
		f.write(page)

	print("✅ REPO_STRUCT.html written (gitignore-style ignores respected)")
