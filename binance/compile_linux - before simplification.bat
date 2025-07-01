@echo off
setlocal

REM ===============================================================================
REM Project: Binance Orderbook Streamer - Cross-platform Linux Binary Build Script
REM 
REM This script builds a self-contained Linux ELF binary of stream_binance.py
REM using Docker Desktop (Linux container) and PyInstaller. It embeds runtime
REM resources such as, `templates/` directory and `get_binance_chart.conf` into
REM the executable via PyInstaller's --add-data option. Designed for use within
REM a conda env matching `requirements.txt`. See `Dockerfile` for details.
REM ===============================================================================

REM ── Configuration ───────────────────────────────────────────────────────────────
REM Docker image tag for build
SET IMAGE_NAME=pyinstaller-stream-binance

REM Name of the final ELF binary
SET OUTPUT_NAME=stream_binance

REM Python script to package
SET SOURCE_FILE=stream_binance.py

REM Folder of HTML templates to embed
SET TEMPLATE_DIR=templates

REM Config file to embed
SET CONF_FILE=get_binance_chart.conf


REM ── [1/3] Build Docker image ──────────────────────────────────────────────────
echo [1/3] Building Docker image...
docker build -t %IMAGE_NAME% . 
IF ERRORLEVEL 1 (
    echo ❌ Docker build failed!
    goto error
)


REM ── [2/3] Run PyInstaller inside Docker ────────────────────────────────────────
echo [2/3] Running PyInstaller inside Docker...
REM The following is one long command; do NOT split with carets (^).
docker run --rm -v %cd%:/app %IMAGE_NAME% bash -lc "cd /app && pyinstaller --onefile --clean --noconfirm --log-level=WARN --name=%OUTPUT_NAME% --hidden-import=jinja2 --add-data=%TEMPLATE_DIR%:%TEMPLATE_DIR% --add-data=%CONF_FILE%:. %SOURCE_FILE% && cp /app/dist/%OUTPUT_NAME% /app/"
IF ERRORLEVEL 1 (
    echo ❌ PyInstaller build failed!
    goto error
)


REM ── [3/3] Clean up intermediate artifacts ───────────────────────────────────────
echo [3/3] Cleaning up build artifacts...
REM Remove PyInstaller build directory
rmdir /s /q build      >nul 2>&1

REM Remove dist directory (binary has been copied out)
rmdir /s /q dist       >nul 2>&1

REM Remove Python bytecode cache
rmdir /s /q __pycache__>nul 2>&1

REM Remove generated spec file
del  /f /q *.spec      >nul 2>&1


echo.
echo ✅ Done! Self-contained Linux binary ready: .\%OUTPUT_NAME%
echo 📦 Embedded resources: %TEMPLATE_DIR%\  %CONF_FILE%
pause
exit /b 0


REM ── Error handler ───────────────────────────────────────────────────────────────
:error
echo.
echo ❌ Build failed! Please inspect the Docker and PyInstaller output above.
pause
exit /b 1
