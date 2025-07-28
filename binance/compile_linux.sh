#!/usr/bin/env bash

pyinstaller \
  --onefile \
  --clean \
  --noconfirm \
  --log-level=ERROR \
  --add-data "app.conf:." \
  --add-data "dashboard.html:." \
  --additional-hooks-dir=. \
  --runtime-hook=sitecustomize.py \
  --hidden-import=numpy \
  --hidden-import=numpy.lib \
  stream_binance.py

mv dist/stream_binance stream_binance
sudo rm -rf build
sudo rm -rf dist
sudo rm stream_binance.spec