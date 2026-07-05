@echo off
REM ============================================================================
REM provision_firestore.bat - ONE-TIME Firestore provisioning for traiga-auditor
REM
REM Run from a regular Command Prompt (cmd.exe) with project-owner rights
REM BEFORE pushing the Firestore migration commit (the deploy flips
REM GOVERNANCE_STORE/SENTINEL_STORE to "firestore"; these databases must
REM exist first).
REM
REM What it does:
REM   1. Enables the Firestore API.
REM   2. Creates the "(default)" database (dashboard data) if missing.
REM      NOTE: "(default)" is the ONLY database covered by the free tier.
REM   3. Creates the "traiga-sentinel" named database (Sentinel telemetry)
REM      if missing - SEPARATE dataset by design (employee-monitoring metadata).
REM   4. Grants the backend service account roles/datastore.user.
REM
REM Rollback of the app is env-var only (GOVERNANCE_STORE/SENTINEL_STORE=sheets);
REM these databases can sit empty at zero cost if you roll back.
REM ============================================================================
setlocal enabledelayedexpansion

set "PROJECT=traiga-auditor"
set "LOCATION=us-central1"

echo Reading backend service account from Secret Manager...
set "LINE="
for /f "delims=" %%L in ('call gcloud secrets versions access latest --secret^=traiga-service-account --project^=%PROJECT% ^| findstr /C:"client_email"') do set "LINE=%%L"
if not defined LINE (
    echo ERROR: could not read client_email from secret traiga-service-account
    exit /b 1
)
set "LINE=!LINE:"=!"
set "LINE=!LINE: =!"
for /f "tokens=2 delims=:," %%A in ("!LINE!") do set "SA=%%A"
echo Backend service account: !SA!

echo.
echo [1/4] Enabling Firestore API...
call gcloud services enable firestore.googleapis.com --project=%PROJECT%
if errorlevel 1 exit /b 1

echo.
echo [2/4] Ensuring (default) database exists...
call gcloud firestore databases describe --database="(default)" --project=%PROJECT% >nul 2>&1
if not errorlevel 1 goto :default_exists
call gcloud firestore databases create --database="(default)" --location=%LOCATION% --type=firestore-native --project=%PROJECT%
if errorlevel 1 exit /b 1
goto :default_done
:default_exists
echo    ^(default^) already exists - skipping
:default_done

echo.
echo [3/4] Ensuring traiga-sentinel database exists...
call gcloud firestore databases describe --database=traiga-sentinel --project=%PROJECT% >nul 2>&1
if not errorlevel 1 goto :sentinel_exists
call gcloud firestore databases create --database=traiga-sentinel --location=%LOCATION% --type=firestore-native --project=%PROJECT%
if errorlevel 1 exit /b 1
goto :sentinel_done
:sentinel_exists
echo    traiga-sentinel already exists - skipping
:sentinel_done

echo.
echo [4/4] Granting roles/datastore.user to backend SA...
call gcloud projects add-iam-policy-binding %PROJECT% --member="serviceAccount:!SA!" --role="roles/datastore.user" --condition=None --quiet >nul
if errorlevel 1 exit /b 1

echo.
echo Done. Databases in project %PROJECT%:
call gcloud firestore databases list --project=%PROJECT% --format="table(name,type,locationId)"
echo.
echo Next: git push origin main - CI deploys with GOVERNANCE_STORE/SENTINEL_STORE=firestore.
endlocal
