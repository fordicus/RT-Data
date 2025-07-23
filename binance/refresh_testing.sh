#!/bin/bash

# Step 1: Navigate to the current user's home directory dynamically
CURRENT_USER=$(whoami)
cd /home/$CURRENT_USER

# Step 2: Forcefully delete the /RT-Data folder
rm -rf /home/$CURRENT_USER/RT-Data

# Step 3: Clone the RT-Data repository using git
git clone https://github.com/fordicus/RT-Data.git

# Step 4: Execute the Python script stream_binance.py
# directly without changing directories
python /home/$CURRENT_USER/RT-Data/binance/stream_binance.py