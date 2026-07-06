@echo off
REM ============================================================
REM  deploy_frontend.bat — frontend ONLY (npm build + Firebase)
REM  Use after any push: the backend deploys itself via GitHub
REM  Actions; this ships the UI in ~2 minutes with no Cloud Build.
REM ============================================================

setlocal
set PROJECT_ID=traiga-auditor
set ROOT_DIR=%~dp0..

cd /d "%ROOT_DIR%\frontend"

echo.
echo [1/2] Building frontend (vite)...
call npm run build
if %errorlevel%==0 goto deploy

echo   Build failed - applying clean-reinstall fix for the npm/rollup bug...
if exist package-lock.json del /f /q package-lock.json
if exist node_modules rmdir /s /q node_modules
call npm install
if %errorlevel% neq 0 goto fail
call npm run build
if %errorlevel% neq 0 goto fail

:deploy
echo.
echo [2/2] Deploying to Firebase Hosting...
cd /d "%ROOT_DIR%"
call firebase deploy --only hosting --project=%PROJECT_ID%
if %errorlevel% neq 0 goto fail

echo.
echo ============================================================
echo  FRONTEND LIVE at https://%PROJECT_ID%.web.app
echo  Hard-refresh the browser (Ctrl+F5) to bypass cached JS.
echo ============================================================
endlocal
exit /b 0

:fail
echo.
echo *** FRONTEND DEPLOY FAILED - see error above ***
endlocal
exit /b 1
