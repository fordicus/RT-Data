r"""................................................................................

How to Use:

	python push.py

................................................................................

Dependency:

	pip install getmac python-dotenv

................................................................................

Functionality:

	This script automates Git operations for the current project directory.
	It configures Git credentials, performs a pull, stages files,
	removes ignored or unwanted files from Git tracking, adds local
	ignore entries to suppress noise, and commits/pushes changes with
	a unique MAC-based timestamp.

................................................................................

IO Structure:

	Input:
		- Working directory files (tracked/untracked)
		- .env file with GIT_EMAIL variable
	Output:
		- Git commit and push to origin/main
		- Cleanup of cached/intermediate files from Git tracking
		- Local suppression of desktop.ini warnings

................................................................................"""

import os
import sys
import time
import pathlib
from datetime import datetime
from getmac import get_mac_address as gma
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────

def run_cmd(cmd: str):
	"""Run and display a system command, with a trailing blank line."""
	print(cmd)
	os.system(cmd)
	print()  # add spacing between commands

def remove_git_cached(target: str):
	"""Remove directory or file from Git index (cache only)."""
	run_cmd(f"git rm --cached {target} -r"
	        if os.path.isdir(target)
	        else f"git rm --cached {target}")

def build_commit_msg():
	"""Construct a unique commit message based on MAC address and timestamp."""
	gma_short = gma().split(':')[-3:]
	return f"{'-'.join(gma_short)} {datetime.now()}"

# ──────────────────────────────────────────────────────────────────────────────

# Load .env file and read email variable
load_dotenv()
GIT_EMAIL = os.getenv("GIT_EMAIL", "default@example.com")

print('-' * 75)

# Git global configuration
run_cmd('git config --global credential.helper store')
run_cmd(f'git config --global user.email "{GIT_EMAIL}"')

# Pull the latest changes
run_cmd('git pull')

# Remove __pycache__ if present
if '__pycache__' in os.listdir():
	run_cmd('rm -rf __pycache__/')

# Stage all files for Git
run_cmd('git add *')

# Directories to forcibly untrack regardless of presence
exclude_dirs = ['.vs', 'x64']

# Files to untrack if present locally
ignore_if_exists = ['desktop.ini']

# Remove listed directories from Git index
for item in exclude_dirs:
	if item in os.listdir():
		remove_git_cached(item)

# Remove listed files if they exist in the working directory
for item in ignore_if_exists:
	if item in os.listdir():
		remove_git_cached(item)

# Add desktop.ini to local .git/info/exclude to silence untracked warning
exclude_file = pathlib.Path('.git/info/exclude')
if exclude_file.exists():
	content = exclude_file.read_text()
	if 'desktop.ini' not in content:
		with exclude_file.open('a') as f:
			f.write('\ndesktop.ini\n')

# Commit and push
commit_msg = build_commit_msg()
run_cmd(f'git commit -m "{commit_msg}: "')
run_cmd('git push origin main')
run_cmd('git log -1')
