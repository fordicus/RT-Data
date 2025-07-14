#!/usr/bin/env bash

# ╔═════════════════════════════════════════════════════════════════════╗
# ║ 🚀 Linux Build Script for stream_binance.py						  	║
# ║																	  	║
# ║ 📦 Creates a self-contained executable (PyInstaller, onefile)		║
# ║ 🧩 Includes: get_binance_chart.conf + stream_binance_dashboard.html	║
# ║ 🧪 Requires: Python 3.9.23 and activated 'binance' environment		║
# ║ 🧱 Assumes: Conda or venv-based activation							║
# ║																	  	║
# ║ 💡 NOTE:															║
# ║   This build uses PyInstaller for portability,						║
# ║   but may be replaced with Nuitka in future builds for:				║
# ║	- Native code compilation (C backend)								║
# ║	- Better runtime performance										║
# ║	- Smaller binary size												║
# ╚═════════════════════════════════════════════════════════════════════╝

set -e
set -o pipefail

# ────────────────────────────────────────────────────────────────
# 🧪 Step 1: Environment validation
# ────────────────────────────────────────────────────────────────

if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
	if [[ "$CONDA_DEFAULT_ENV" != "binance" ]]; then
		echo "❌ Conda environment is '$CONDA_DEFAULT_ENV', expected 'binance'"
		exit 1
	fi
	echo "📦 Conda environment: $CONDA_DEFAULT_ENV"
	PYTHON="$(which python)"
elif [[ -n "$VIRTUAL_ENV" ]]; then
	ENV_NAME=$(basename "$VIRTUAL_ENV")
	if [[ "$ENV_NAME" != "binance" ]]; then
		echo "❌ Virtualenv is '$ENV_NAME', expected 'binance'"
		exit 1
	fi
	echo "📦 Virtualenv: $ENV_NAME"
	PYTHON="$VIRTUAL_ENV/bin/python"
else
	echo "❌ No virtual environment or conda environment detected."
	echo "💡 Please activate the 'binance' environment before running this script."
	exit 1
fi

# Check Python version
PY_VERSION=$($PYTHON -c 'import platform; print(platform.python_version())')
if [[ "$PY_VERSION" != "3.9.23" ]]; then
	echo "❌ Python version is $PY_VERSION — expected 3.9.23"
	exit 1
fi
echo "🐍 Python version check passed: $PY_VERSION"

# ────────────────────────────────────────────────────────────────
# 🧹 Step 2: Pre-build cleanup
# ────────────────────────────────────────────────────────────────

echo "🧹 Pre-build cleanup..."
rm -rf build/
rm -rf dist/
rm -f *.spec
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

# ────────────────────────────────────────────────────────────────
# ⚙️ Step 3: Build executable
# ────────────────────────────────────────────────────────────────

echo "⚙️ Building self-contained executable..."
pyinstaller \
  --name stream_binance \
  --onefile \
  --clean \
  --noconfirm \
  --hidden-import=uvicorn \
  --add-data "$(python -m certifi):." \
  --add-data "stream_binance_dashboard.html:." \
  --add-data "get_binance_chart.conf:." \
  stream_binance.py

# ────────────────────────────────────────────────────────────────
# 🧹 Step 4: Post-build cleanup
# ────────────────────────────────────────────────────────────────

echo "🧹 Post-build cleanup..."

# Move final binary to current directory
mv dist/stream_binance ./stream_binance

# Remove leftover artifacts
rm -rf build/
rm -rf dist/
rm -f *.spec
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

# ────────────────────────────────────────────────────────────────
# ✅ Done
# ────────────────────────────────────────────────────────────────

echo ""
echo "✅ Build complete!"
echo "📦 Output binary: ./stream_binance"
echo "🧪 Test it with: ./stream_binance"
