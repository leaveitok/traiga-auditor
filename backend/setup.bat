@echo off
REM AI Transparency Auditor v2 — Backend Setup Script
REM Run this from the backend\ directory: setup.bat

echo === Step 1: Installing Python dependencies ===
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python 3.11+ is on your PATH.
    pause & exit /b 1
)

echo.
echo === Step 2: Installing Playwright browser ===
playwright install chromium
if %errorlevel% neq 0 (
    echo WARNING: Playwright install failed. Live crawling will fall back to static mode.
)

echo.
echo === Step 3: Checking for service_account.json ===
if not exist "service_account.json" (
    echo.
    echo *** ACTION REQUIRED ***
    echo Copy your Google service account JSON key into this folder as:
    echo     %~dp0service_account.json
    echo Then re-run this script OR just start the server with the command below.
    echo.
) else (
    echo service_account.json found OK
)

echo.
echo === Setup complete ===
echo.
echo To start the API server, run:
echo     uvicorn main:app --reload --host 0.0.0.0 --port 8000
echo.
echo API docs will be at: http://localhost:8000/api/docs
pause
