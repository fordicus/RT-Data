#!/bin/bash

clear

CURRENT_USER=$(whoami)
cd /home/$CURRENT_USER

rm -rf /home/$CURRENT_USER/RT-Data

git clone https://github.com/fordicus/RT-Data.git

# python /home/$CURRENT_USER/RT-Data/binance/stream_binance.py