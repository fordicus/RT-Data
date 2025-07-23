#!/bin/bash

# ----------------------------------------------------
# purge_testing.sh
# ----------------------------------------------------
# Purpose:
#   Clean up test artifacts after running `stream_binance`.
#   Deletes the following if they exist:
#     - data/                (directory)
#     - stream_binance       (binary or script)
#     - stream_binance.log   (log file)
#
# Context:
#   Windows: Development environment
#   Ubuntu:  Production environment
#
# Usage:
#   Run this script to streamline repeated test cycles.
#   It checks for the above files/directories and
#   prompts for deletion if found.
# ----------------------------------------------------

# List of targets to check
TARGETS=("data" "stream_binance" "stream_binance.log")

# Check which ones exist
EXISTING=()
for target in "${TARGETS[@]}"; do
    if [ -e "$target" ]; then
        EXISTING+=("$target")
    fi
done

# Prompt user before deletion
if [ ${#EXISTING[@]} -gt 0 ]; then
    echo "The following items exist:"
    for item in "${EXISTING[@]}"; do
        echo "  - $item"
    done
    read -p "Do you want to delete them? (Y/n): " answer
    if [[ "$answer" =~ ^[Yy]$ || -z "$answer" ]]; then
        [ -d "data" ] && rm -rf data
        [ -f "stream_binance" ] && rm stream_binance
        [ -f "stream_binance.log" ] && rm stream_binance.log
        echo "Deletion complete."
    else
        echo "Deletion canceled."
    fi
else
    echo "No items to delete."
fi
