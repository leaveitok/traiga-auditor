@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == CRITICAL: fix the backend deploy that has been RED since 01.1 ===========
REM
REM ROOT CAUSE (found by reading the Actions run): the backend "Deploy to Cloud Run"
REM job has failed on EVERY release since 01.1 - the backend has been frozen at commit
REM 3986274 (July 19) while the frontend kept deploying. So none of releases 01.1-01.6
REM (release stamping, OAuth two-methods, Evidence Bundles Phases 1-2) is actually live
REM on the API. The empty audience picker was the symptom: /api/reports/presets does not
REM exist on the deployed backend.
REM
REM THE BUG: in 01.1 I added to deploy.yml:
REM     echo "APP_RELEASE: $(cat VERSION)"
REM which writes  APP_RELEASE: 01.6  (UNQUOTED) into deploy/env.yaml. gcloud reads that
REM file as YAML, and YAML parses 01.6 as the FLOAT 1.6, not a string. gcloud
REM --env-vars-file requires string values, so it rejected it with an argument error -
REM exit code 2 - and the deploy died before ever updating Cloud Run. (The test job was
REM green the whole time; only the deploy step failed, which is why it stayed hidden.)
REM The existing REQUIRE_AUTH: "true" and SCAN_CADENCE_HOURS: "24" are quoted for exactly
REM this reason; I added APP_RELEASE unquoted. GIT_SHA survived only because a commit SHA
REM contains letters, so YAML keeps it a string.
REM
REM THE FIX: quote the value (and guard a missing file):
REM     echo "APP_RELEASE: \"$(cat VERSION 2>/dev/null || echo dev)\""
REM -> writes  APP_RELEASE: "01.6"  -> YAML string -> gcloud accepts. Verified by
REM simulating the exact CI shell and YAML-parsing the result.
REM
REM SECOND FIX (frontend): the Reports store swallowed a failed /presets call and showed
REM an empty audience list with no explanation - which is how this whole outage looked
REM like a "Reports bug". It now surfaces the error, and a 404 says the backend is a
REM release behind and to check Settings -> Version & Build.
REM
REM WHAT THIS PUSH DOES: the corrected deploy.yml runs on THIS push, so the deploy job
REM finally succeeds and Cloud Run jumps from 3986274 straight to this commit - lighting
REM up every backend feature from 01.1 through here at once.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_deploy_fix.bat" "Fix backend deploy red since 01.1: quote APP_RELEASE in env.yaml (YAML float coercion); surface Reports preset-load error"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_deploy_fix.bat" ".github/workflows/deploy.yml" "frontend/src/stores/reports.js" "frontend/src/views/ReportsView.vue"

echo [2/6] Staging...
git add %FILES%
if errorlevel 1 goto :fail
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [3/6] Untracked-source guard...
set ORPHAN=0
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &set ORPHAN=1 )
)
if "!ORPHAN!"=="1" goto :orphanfail
echo   No untracked source files outstanding.

echo [4/6] Backend tests...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [5/6] Committing as release !RELEASE!...
git commit -m "fix(ci): quote APP_RELEASE in env.yaml - unblocks backend deploy red since 01.1 (!RELEASE!)" -m "The backend Deploy to Cloud Run job has failed on every release since 01.1, leaving the deployed API frozen at commit 3986274 while the frontend kept shipping - so none of release stamping, the OAuth two-methods path, or Evidence Bundles Phases 1 and 2 was actually live, and the empty Reports audience picker was the symptom because /api/reports/presets did not exist on the server. The cause was a line added to deploy.yml in 01.1 that wrote APP_RELEASE: 01.6 unquoted into the env-vars file; gcloud reads that file as YAML, which parses 01.6 as the float 1.6, and gcloud --env-vars-file rejects a non-string value with an argument error (exit code 2), killing the deploy step before Cloud Run was ever updated. The test job was green throughout, which is why the failure stayed hidden behind a green frontend run. The value is now quoted, with a fallback for a missing file, so the file contains APP_RELEASE: \"01.6\" and YAML keeps it a string; this was verified by simulating the CI shell and parsing the result. The Reports store also no longer swallows a failed presets call - it surfaces the error, and a 404 explains that the backend is a release behind and to check Settings. This push runs the corrected workflow, so the deploy finally succeeds and Cloud Run advances from 3986274 straight to this commit." -m "Release: !RELEASE!" -m "Ship-Bat: ship_deploy_fix.bat"
if errorlevel 1 goto :fail

echo [6/6] Verify commit matches disk, then push...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo.
echo  THIS IS THE IMPORTANT ONE - WATCH IT:
echo   Open GitHub Actions. The "Deploy to Cloud Run" run
echo   for this commit must go GREEN on BOTH jobs
echo   (Backend tests AND Build ^& Deploy). Every release
echo   since 01.1 died on Build ^& Deploy - this is the fix.
echo.
echo  THEN CONFIRM IT LANDED:
echo   1. Settings -^> Version ^& Build now shows a RELEASE
echo      number (not a bare SHA) matching !RELEASE!.
echo   2. Reports -^> pick a city: audience cards appear.
echo   3. api/health now returns a "release" field.
echo ==================================================
goto :eof

:gitfail
echo *** git HEAD unreadable. ***
exit /b 1
:stampfail
echo *** Release stamp failed - nothing committed. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:nothingfail
echo *** Nothing staged. Rolling the stamp back. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:orphanfail
echo *** The untracked source listed above would be MISSING in prod. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:testfail
echo *** TESTS FAILED - not committing. Rolling the stamp back. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:verifyfail
echo *** Commit does not match disk - NOT pushing. ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
