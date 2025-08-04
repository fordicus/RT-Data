# refresh_testing.sh

clear
# sudo rm -rf data
# sudo rm -rf stream_binance
# sudo rm -rf stream_binance.log

# Re-clone the Repository
CURRENT_USER=$(whoami)
cd /home/$CURRENT_USER
sudo rm -rf /home/$CURRENT_USER/RT-Data
git clone https://github.com/fordicus/RT-Data.git
