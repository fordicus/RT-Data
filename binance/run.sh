#!/usr/bin/env bash

# sudo chrt -f 80 nice -n -19 ionice -c1 -n0 ./stream_binance
sudo chrt -f 80 nice -n -19 ionice -c1 -n0 $(which python) stream_binance.py
