@echo off
setlocal

REM ══════════════════════════════════════════════════════
REM 🐧 Compile Linux ELF Binary via Docker + PyInstaller
REM Embeds templates/ and get_binance_chart.conf self-contained
REM Author: Hyo | Windows + Docker Desktop
REM ══════════════════════════════════════════════════════

REM ── Configuration ────────────────────────────────────────
SET IMAGE_NAME=pyinstaller-stream-binance
SET OUTPUT_NAME=stream_binance
SET SOURCE_FILE=stream_binance.py
SET TEMPLATE_DIR=templates
SET CONF_FILE=get_binance_chart.conf

REM ── [1/3] Build Docker image ─────────────────────────────
echo [1/3] Building Docker image...
docker build -t %IMAGE_NAME% . || goto error

REM ── [2/3] Run PyInstaller inside Docker ───────────────────
echo [2/3] Running PyInstaller inside Docker...
docker run --rm -v %cd%:/app %IMAGE_NAME% bash -lc "cd /app && pyinstaller --onefile --clean --noconfirm --log-level=WARN --name=%OUTPUT_NAME% --hidden-import=jinja2 --add-data=%TEMPLATE_DIR%:%TEMPLATE_DIR% --add-data=%CONF_FILE%:. %SOURCE_FILE% && cp /app/dist/%OUTPUT_NAME% /app/" || goto error

REM ── [3/3] Clean up intermediate artifacts ─────────────────
echo [3/3] Cleaning up build artifacts...
rmdir /s /q build      >nul 2>&1
rmdir /s /q dist       >nul 2>&1
rmdir /s /q __pycache__>nul 2>&1
del  /f /q *.spec      >nul 2>&1

echo.
echo ✅ Done! Self-contained Linux binary ready: .\%OUTPUT_NAME%
echo 📦 Embedded resources: %TEMPLATE_DIR%\  %CONF_FILE%
pause
exit /b 0

REM ── Error handler ────────────────────────────────────────
:error
echo.
echo ❌ Build failed! Please inspect the Docker/PyInstaller output above.
pause
exit /b 1
