```bash
#!/usr/bin/env bash
#———————————————————————————————————————————————————————————————————————————————
# Linux Build Script for stream_binance.py  (Nuitka one‑file build)
#
# Creates a self‑contained native executable (C++ backend, onefile)
# Includes: app.conf + dashboard.html + certifi CA bundle
# Statically embeds critical runtime packages (uvicorn, fastapi, websockets,
#     uvloop, orjson, psutil) to avoid “module not found” surprises.
# Requires: Python 3.11.13 and activated 'binance' environment
# Works with Conda or venv activation
#———————————————————————————————————————————————————————————————————————————————

set -e
set -o pipefail
DEBUG=true
if [[ $DEBUG == true ]]; then
  set -x
fi

export CC="ccache gcc"
export CXX="ccache g++"

>&2 echo "[DEBUG] Script started: $(date)"
>&2 echo "[DEBUG] CONDA_DEFAULT_ENV=$CONDA_DEFAULT_ENV"

#———————————————————————————————————————————————————————————————————————————————
# 1) Environment validation
#———————————————————————————————————————————————————————————————————————————————
if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
	if [[ "$CONDA_DEFAULT_ENV" != "binance" ]]; then
		echo "Conda environment is '$CONDA_DEFAULT_ENV', expected 'binance'"
		exit 1
	fi
	echo "Conda environment: $CONDA_DEFAULT_ENV"
	PYTHON="/home/c01hyka/anaconda3/envs/binance/bin/python"
elif [[ -n "$VIRTUAL_ENV" ]]; then
	ENV_NAME=$(basename "$VIRTUAL_ENV")
	if [[ "$ENV_NAME" != "binance" ]]; then
		echo "Virtualenv is '$ENV_NAME', expected 'binance'"
		exit 1
	fi
	echo "Virtualenv: $ENV_NAME"
	PYTHON="$VIRTUAL_ENV/bin/python"
else
	echo "No virtual environment or conda environment detected."
	echo "Please activate the 'binance' environment before running this script."
	exit 1
fi

# —— Python version check ————————————————————————————————
REQ_PY="3.11.13"
PY_VERSION=$($PYTHON -c 'import platform; print(platform.python_version())')
if [[ "$PY_VERSION" != "$REQ_PY" ]]; then
	echo "Python version is $PY_VERSION — required $REQ_PY"
	exit 1
fi
echo "Python version check passed: $PY_VERSION"

#———————————————————————————————————————————————————————————————————————————————
# 2) Build with Nuitka
#———————————————————————————————————————————————————————————————————————————————
echo "Building native one‑file executable (this may take a while)…"
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
  # Avoids accidental inclusion of standard lib modules not explicitly followed.
  --noinclude-default-mode=nofollow \
  --jobs=$(nproc) \
  --static-libpython=no \
  stream_binance.py

#———————————————————————————————————————————————————————————————————————————————
# 3) Resource check
#———————————————————————————————————————————————————————————————————————————————
if [[ -f _test_resource_path.py ]]; then
    $PYTHON _test_resource_path.py || echo "[WARNING] Embedded resource test failed"
else
    echo "[INFO] _test_resource_path.py not found, skipping resource check."
fi

#———————————————————————————————————————————————————————————————————————————————
# 4) Post‑build cleanup
#———————————————————————————————————————————————————————————————————————————————
echo "Cleaning up build artifacts…"
rm -rf stream_binance.dist stream_binance.onefile-build
rm -f stream_binance.spec
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} +

#———————————————————————————————————————————————————————————————————————————————
# Done
#———————————————————————————————————————————————————————————————————————————————
echo ""
echo "Build complete!"
echo "Output binary: ./stream_binance"
echo "Run it with: ./stream_binance"
```
