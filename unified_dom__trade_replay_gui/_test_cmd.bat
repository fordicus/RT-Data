@echo off

REM 프론트엔드 (일반 CMD)
start "Frontend" cmd.exe /k "cd frontend && npm run dev"

REM 백엔드 (Anaconda-aware CMD - 한 줄로!)
start "Backend" cmd.exe /k "call C:\Users\fordi\anaconda3\Scripts\activate.bat C:\Users\fordi\anaconda3 && cd /D C:\workspace\RT-Data\unified_dom__trade_replay_gui && uvicorn backend.app:app --reload"
