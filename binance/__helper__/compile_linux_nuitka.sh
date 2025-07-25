#!/usr/bin/env bash

#———————————————————————————————————————————————————————————————————————————————
# Linux Build Script for stream_binance.py (Nuitka one-file build)
#
# Purpose: Creates a self-contained native executable (C++ backend, onefile)
# Includes: app.conf + dashboard.html + certifi CA bundle
# Embeds: uvicorn, fastapi, websockets, uvloop, orjson, psutil
# Requires: Python 3.11.13 and activated 'binance' environment
# Compatible: Conda or venv activation
#———————————————————————————————————————————————————————————————————————————————

set -e
set -o pipefail
DEBUG=false
if [[ $DEBUG == true ]]; then
  set -x
fi

which ccache &>/dev/null && echo "[INFO] ccache is available and will be used automatically"

>&2 echo "[DEBUG] Script started: $(date)"
>&2 echo "[DEBUG] CONDA_DEFAULT_ENV=$CONDA_DEFAULT_ENV"

#———————————————————————————————————————————————————————————————————————————————
# 1) Environment validation and Python path detection
#———————————————————————————————————————————————————————————————————————————————

echo "Validating build environment..."

if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
	if [[ "$CONDA_DEFAULT_ENV" != "binance" ]]; then
		echo "[ERROR] Conda environment is '$CONDA_DEFAULT_ENV', expected 'binance'"
		echo "		Please run: conda activate binance"
		exit 1
	fi
	if [[ -n "$CONDA_PREFIX" ]]; then
		PYTHON="$CONDA_PREFIX/bin/python"
		echo "[OK] Using Conda environment: $CONDA_DEFAULT_ENV"
		echo "	 Python path is '$PYTHON'"
	else
		echo "[ERROR] CONDA_PREFIX not set (conda environment issue)"
		echo "		Try: conda deactivate && conda activate binance"
		exit 1
	fi
elif [[ -n "$VIRTUAL_ENV" ]]; then
	ENV_NAME=$(basename "$VIRTUAL_ENV")
	if [[ "$ENV_NAME" != "binance" ]]; then
		echo "[ERROR] Virtualenv is '$ENV_NAME', expected 'binance'"
		echo "		Please activate the correct environment"
		exit 1
	fi
	echo "[OK] Using Virtualenv: $ENV_NAME"
	PYTHON="$VIRTUAL_ENV/bin/python"
	echo "	 Python path is '$PYTHON'"
else
	echo "[ERROR] No virtual environment or conda environment detected."
	echo "		Please activate the 'binance' environment before running this script."
	echo "		- Conda: conda activate binance"
	echo "		- Venv:  source binance/bin/activate"
	exit 1
fi

#———————————————————————————————————————————————————————————————————————————————
# 2) Python version verification
#———————————————————————————————————————————————————————————————————————————————

echo "Verifying Python version..."
REQ_PY="3.11.13"
PY_VERSION=$($PYTHON -c 'import platform; print(platform.python_version())')
if [[ "$PY_VERSION" != "$REQ_PY" ]]; then
	echo "[ERROR] Python version mismatch:"
	echo "		Current: $PY_VERSION"
	echo "		Required: $REQ_PY"
	echo "		Please install the correct Python version in your environment"
	exit 1
fi
echo "[OK] Python version check passed: $PY_VERSION"

#———————————————————————————————————————————————————————————————————————————————
# 3) Native compilation with Nuitka
#———————————————————————————————————————————————————————————————————————————————

echo ""
echo "Starting native compilation (this may take 3-5 minutes)..."
echo "Using $(nproc) CPU cores for parallel compilation"
echo ""

# The --noinclude-default-mode=nofollow flag prevents accidental inclusion of 
# standard library modules that aren't explicitly followed, reducing binary size
stdbuf -oL -eL "$PYTHON" -m nuitka \
  --onefile \
  --output-filename=stream_binance \
  --include-data-file=dashboard.html=dashboard.html \
  --include-data-file=app.conf=app.conf \
  --include-package=certifi \
  --include-module=uvicorn \
  --include-module=fastapi \
  --include-package=websockets \
  --include-module=uvloop \
  --include-module=orjson \
  --include-module=psutil \
  --follow-imports \
  --assume-yes-for-downloads \
  --lto=no \
  --noinclude-default-mode=nofollow \
  --jobs=$(nproc) \
  --static-libpython=no \
  stream_binance.py

#———————————————————————————————————————————————————————————————————————————————
# 4) Embedded resource verification
#———————————————————————————————————————————————————————————————————————————————

echo "Verifying embedded resources..."
if [[ -f test_resource_path.py ]]; then
	if $PYTHON test_resource_path.py; then
		echo "[OK] Embedded resource test passed"
	else
		echo "[WARNING] Embedded resource test failed - binary may not work correctly"
	fi
else
	echo "[INFO] test_resource_path.py not found, skipping resource check."
fi

#———————————————————————————————————————————————————————————————————————————————
# 5) Post-build cleanup
#———————————————————————————————————————————————————————————————————————————————

echo "Cleaning up build artifacts..."
rm -rf stream_binance.dist stream_binance.onefile-build
rm -f stream_binance.spec
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +
echo "[OK] Cleanup completed"

#———————————————————————————————————————————————————————————————————————————————
# 6) Build completion summary
#———————————————————————————————————————————————————————————————————————————————

if [[ -f "./stream_binance" ]]; then
	BINARY_SIZE=$(du -h "./stream_binance" | cut -f1)
	echo ""
	echo "=============================================="
	echo "BUILD SUCCESSFUL!"
	echo "=============================================="
	echo "Output binary: ./stream_binance"
	echo "Binary size: $BINARY_SIZE"
	echo "Python version: $PY_VERSION"
	echo "=============================================="
	echo ""
else
	echo ""
	echo "=============================================="
	echo "BUILD FAILED!"
	echo "=============================================="
	echo "The binary './stream_binance' was not created."
	echo "Check the compilation output above for errors."
	echo "=============================================="
	exit 1
fi