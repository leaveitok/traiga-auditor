@echo off
REM =============================================================================
REM deploy-frontend.bat - Build + publish ONLY the Vue frontend to Firebase.
REM Self-heals the npm optional-dependency (rollup) bug that breaks `npm ci`
REM on Windows (npm issue #4828). Run from cmd:
REM   cd "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
REM   deploy\deploy-frontend.bat
REM =============================================================================
setlocal
set PROJECT_ID=traiga-auditor
set ROOT_DIR=%~dp0..
set FRONTEND_DIR=%ROOT_DIR%\frontend

cd /d "%FRONTEND_DIR%"

echo [1/3] Building frontend (using existing node_modules)...
call npm run build
if %errorlevel%==0 goto deploy

echo.
echo Build failed. Applying clean-reinstall fix for the npm/rollup
echo optional-dependency bug, then retrying...
if exist package-lock.json del /f /q package-lock.json
if exist node_modules rmdir /s /q node_modules
call npm install
if %errorlevel% neq 0 goto error
call npm run build
if %errorlevel% neq 0 goto error

:deploy
cd /d "%ROOT_DIR%"
echo [2/3] Publishing to Firebase Hosting...
call firebase deploy --only hosting --project=%PROJECT_ID%
if %errorlevel% neq 0 goto error

echo.
echo [3/3] DONE. Hard-refresh https://%PROJECT_ID%.web.app  (Ctrl+Shift+R)
echo   The title bar should now read "TRAIGA Auditor".
goto end

:error
echo.
echo ============================================================
echo   FRONTEND DEPLOY FAILED - copy ALL the red/error text above
echo   and send it to me. Do not close this window first.
echo ============================================================
exit /b 1

:end
endlocal
