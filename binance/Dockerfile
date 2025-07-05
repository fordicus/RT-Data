# ================================================================================
# Project: Binance Orderbook Streamer - Dockerfile for PyInstaller Build Environment
#
# Purpose:
#  This Dockerfile defines a minimal Linux container for building a self-contained
#  Linux ELF binary of stream_binance.py. It installs system dependencies, Python
#  runtime, project requirements, and PyInstaller, then runs PyInstaller to package
#  the app along with templates/ and get_binance_chart.conf.
#
# Usage:
#  On Windows, simply run compile_linux.bat in the project root. That script
#  references this Dockerfile and will handle building the Docker image,
#  running PyInstaller, extracting the binary, and cleaning up—all automatically.
#  No manual docker build or docker run commands are needed.
#
# Note:
#  - The Docker host must support Linux containers (e.g., Docker Desktop in Linux mode).
#  - The build context is the current folder; source and resources are copied into /app.
#  - The final binary appears in /app/dist/stream_binance after pyinstaller runs.
#
# DO NOT ALTER THE COMMAND LINES BELOW — they must remain unbroken to avoid shell parsing issues.
# ================================================================================

FROM python:3.11-slim

# Set working directory for all subsequent commands
WORKDIR /app

# Install essential build tools: compiler, curl, zip for packaging, git for version control
RUN apt-get update && apt-get install -y build-essential curl zip git && pip install --upgrade pip

# Copy requirements file and install Python dependencies
# The requirements.txt pins versions for Python 3.9.23 environment matching the conda setup.
COPY requirements.txt .
RUN pip install -r requirements.txt pyinstaller

# Copy all source code and resource files (templates/, get_binance_chart.conf, etc.) into the container
COPY . .

# Run PyInstaller to produce a single self-contained Linux executable
# Embeds HTML templates and configuration file via --add-data flags.
# The --onefile option bundles everything; --clean removes temporary files.
RUN pyinstaller --onefile --clean --noconfirm --log-level=ERROR --hidden-import=jinja2 --add-data templates:templates --add-data get_binance_chart.conf:. stream_binance.py

# Default command prints completion message; binary is available under /app/dist/stream_binance
CMD ["echo", "Build complete! Find binary in /app/dist"]
