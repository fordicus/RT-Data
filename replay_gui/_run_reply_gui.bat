@echo off
REM ============================================================================
REM Unified launcher for FastAPI + Vite development servers
REM 
REM ⚠️ MUST be run from the current folder
REM 
REM Conda env must be manually pre-activated or invoked explicitly.
REM This script assumes:
REM   - backend.app:app is discoverable from WORKDIR
REM   - Vite and Node are properly installed in frontend/
REM ============================================================================

REM Get current working directory (RT-Data\chart_dom_replay_gui)
set "WORKDIR=%cd%"

REM Launch frontend (Vite dev server)
start "Frontend" cmd.exe /K ^
"cd /D %WORKDIR%\frontend ^&^& npm run dev"

REM Launch backend (FastAPI) — run from WORKDIR to preserve module context
start "Backend" cmd.exe /K ^
"call C:\Users\fordi\anaconda3\Scripts\activate.bat C:\Users\fordi\anaconda3 ^&^& ^
cd /D %WORKDIR% ^&^& ^
uvicorn backend.app:app --reload"

REM Display endpoints
echo [INFO] FastAPI:   http://localhost:8000
echo [INFO] Frontend:  http://localhost:5173
