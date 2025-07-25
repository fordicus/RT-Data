#!/bin/bash

clear

CURRENT_USER=$(whoami)
cd /home/$CURRENT_USER

sudo rm -rf /home/$CURRENT_USER/RT-Data

git clone https://github.com/fordicus/RT-Data.git

cd /home/$CURRENT_USER/RT-Data/binance/

# python /home/$CURRENT_USER/RT-Data/binance/stream_binance.py