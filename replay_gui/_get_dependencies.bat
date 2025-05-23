@echo off
setlocal

rem ============================================================================
rem Script: _get_dependencies.bat
rem Purpose:
rem     Collect essential dependency versions for both frontend and backend.
rem     Meant to be executed from the root of the project repository.
rem
rem Output:
rem     Printed to CMD only (no file is written).
rem     Includes frontend (Node.js/Vite/TS) and backend (Python/FastAPI).
rem
rem Note:
rem     - Must be run from the folder containing `frontend/` directory.
rem     - `npm list --depth=0` assumes packages are installed.
rem     - Uses `call` and `if errorlevel` for robustness.
rem ============================================================================

echo ==========================================================
echo [FRONTEND DEPENDENCIES]
echo ==========================================================

if not exist frontend (
	echo ERROR: 'frontend' folder not found.
	exit /b
)

cd frontend
echo STEP 1: Entered frontend → %CD%

echo.
echo STEP 2: Node version
call node --version
if errorlevel 1 (
	echo ERROR: node --version failed
	exit /b
)
echo STEP 2 OK

echo.
echo STEP 3: NPM version
call npm -v
if errorlevel 1 (
	echo ERROR: npm -v failed
	exit /b
)
echo STEP 3 OK

echo.
echo STEP 4: Installed packages (top-level)
call npm list --depth=0
if errorlevel 1 (
	echo ERROR: npm list failed
	exit /b
)
echo STEP 4 OK

echo.
echo STEP 5: TypeScript version
call npx --yes tsc --version
if errorlevel 1 (
	echo ERROR: npx tsc --version failed
	exit /b
)
echo STEP 5 OK

echo.
echo STEP 6: Vite version
call npx --yes vite --version
if errorlevel 1 (
	echo ERROR: npx vite --version failed
	exit /b
)
echo STEP 6 OK

cd ..
echo STEP 7: Returned to root → %CD%

echo ==========================================================
echo [BACKEND DEPENDENCIES]
echo ==========================================================

echo.
echo STEP 8: Python version
call python --version
if errorlevel 1 (
	echo ERROR: python --version failed
	exit /b
)
echo STEP 8 OK

echo.
echo STEP 9: PIP version
call pip --version
if errorlevel 1 (
	echo ERROR: pip --version failed
	exit /b
)
echo STEP 9 OK

echo.
echo STEP 10: FastAPI version
call pip show fastapi | findstr /B /I "Name Version"
if errorlevel 1 (
	echo ERROR: pip show fastapi failed
	exit /b
)
echo STEP 10 OK

echo.
echo STEP 11: pandas version
call pip show pandas | findstr /B /I "Name Version"
if errorlevel 1 (
	echo ERROR: pip show pandas failed
	exit /b
)
echo STEP 11 OK

echo.
echo STEP 12: uvicorn version
call pip show uvicorn | findstr /B /I "Name Version"
if errorlevel 1 (
	echo ERROR: pip show uvicorn failed
	exit /b
)
echo STEP 12 OK

REM STEP 13: Note built-in modules used (not detected via pip)

echo STEP 13: Built-in Python modules used:
echo   - json     (for NDJSON line-by-line DOM parsing)
echo   - bisect   (for fast binary search alignment in tick→DOM matching)
echo STEP 13 OK

echo.
echo ✅ All dependency checks completed successfully.
