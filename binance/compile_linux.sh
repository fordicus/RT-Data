```bash
#!/usr/bin/env bash
#———————————————————————————————————————————————————————————————————————————————
# 🚀 Linux Build Script for stream_binance.py  (Nuitka one‑file build)
#
# 📦 Creates a self‑contained native executable (C++ backend, onefile)
# 🧩 Includes: app.conf + dashboard.html + certifi CA bundle
# 🔒 Statically embeds critical runtime packages (uvicorn, fastapi, websockets,
#     uvloop, orjson, psutil) to avoid “module not found” surprises.
# 🧪 Requires: Python 3.11.13 and activated 'binance' environment
# 🧱 Works with Conda or venv activation
#———————————————————————————————————————————————————————————————————————————————

set -e
set -o pipefail

#———————————————————————————————————————————————————————————————————————————————
# 🧪 1) Environment validation
#———————————————————————————————————————————————————————————————————————————————
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

# —— Python version check ————————————————————————————————
REQ_PY="3.11.13"
PY_VERSION=$($PYTHON -c 'import platform; print(platform.python_version())')
if [[ "$PY_VERSION" != "$REQ_PY" ]]; then
	echo "❌ Python version is $PY_VERSION — required $REQ_PY"
	exit 1
fi
echo "🐍 Python version check passed: $PY_VERSION"

#———————————————————————————————————————————————————————————————————————————————
# 🧹 2) Pre‑build cleanup
#———————————————————————————————————————————————————————————————————————————————
echo "🧹 Pre‑build cleanup…"
rm -rf build/ dist/ *.spec *.build/ ./*.dist ./*.build
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

#———————————————————————————————————————————————————————————————————————————————
# 📦 3) Nuitka availability
#———————————————————————————————————————————————————————————————————————————————
if ! command -v nuitka3 &>/dev/null; then
	echo "📦 Installing Nuitka (and wheelhouse‑needed back‑ends)…"
	$PYTHON -m pip install --upgrade pip
	$PYTHON -m pip install --upgrade nuitka
fi

#———————————————————————————————————————————————————————————————————————————————
# ⚙️ 4) Build with Nuitka
#———————————————————————————————————————————————————————————————————————————————
echo "⚙️ Building native one‑file executable (this may take a while)…"
nuitka3 \
  --onefile \
  --output-filename=stream_binance \
  --include-data-file=dashboard.html=dashboard.html \
  --include-data-file=app.conf=app.conf \
  --include-package=certifi \
  --include-module=uvicorn \
  --include-module=fastapi \
  --include-module=websockets \
  --include-module=uvloop \
  --include-module=orjson \
  --include-module=psutil \
  --follow-imports \
  --assume-yes-for-downloads \
  --clang \
  --lto=yes \
  --jobs=$(nproc) \
  stream_binance.py

#———————————————————————————————————————————————————————————————————————————————
# 🔍 5) Runtime resource sanity check
#———————————————————————————————————————————————————————————————————————————————
echo "🔍 Verifying embedded resources in binary…"
if ! strings ./stream_binance | grep -q "dashboard.html"; then
	echo "❌ Embedded resources check failed (dashboard.html not found in binary)"
	exit 1
fi
if ! strings ./stream_binance | grep -q "app.conf"; then
	echo "❌ Embedded resources check failed (app.conf not found in binary)"
	exit 1
fi
echo "✅ Resource check passed"

#———————————————————————————————————————————————————————————————————————————————
# 🧹 6) Post‑build cleanup
#———————————————————————————————————————————————————————————————————————————————
echo "🧹 Cleaning up build artifacts…"
rm -rf *.build/ ./*.dist build/ dist/
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

#———————————————————————————————————————————————————————————————————————————————
# ✅ Done
#———————————————————————————————————————————————————————————————————————————————
echo ""
echo "✅ Build complete!"
echo "📦 Output binary: ./stream_binance"
echo "🧪 Run it with: ./stream_binance"
```
