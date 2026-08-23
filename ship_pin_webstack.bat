@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice PIN-1: pin the backend web stack as a set ------------------------
REM Root cause of the 2026-08-23 9-test 422 failure: '>=' ranges let the LOCAL
REM env keep an old fastapi (0.115.x) while CI resolved a new one. fastapi
REM 0.115.x cannot resolve PEP-563 string annotations through slowapi's
REM @limiter.limit wrapper, so body models silently became QUERY params ->
REM 422 loc ["query","packet"] locally while CI stayed green. Same class as
REM the playwright==1.44.0 pin already in this file (2026-07-04 lesson).
REM  * requirements.txt: fastapi==0.141.1, starlette==1.6.0 (now explicit),
REM    pydantic==2.10.4, slowapi==0.1.10. Everything else untouched.
REM Verified in sandbox 2026-08-23: FRESH venv installed strictly from the new
REM requirements.txt resolves cleanly and the full suite is 331/331 green on
REM exactly these versions. The Deploy Backend CI run is the authoritative
REM gate for the Docker/Cloud Run python.
REM This bat ALIGNS THE LOCAL ENV to the pins (step 2) - that is the point of
REM the slice: local and CI install the same proven window from here on.

echo [0/7] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Pre-flight: prove the pin edit is applied (fail loudly on a no-op)...
findstr /C:"fastapi==0.141.1" "backend\requirements.txt" >nul || ( echo *** requirements.txt pin edit not applied. & exit /b 1 )
findstr /C:"starlette==1.6.0" "backend\requirements.txt" >nul || ( echo *** starlette pin missing. & exit /b 1 )
echo   Pins present.

echo [2/7] Aligning the LOCAL env to the pinned set (idempotent when already there)...
REM NAMED pins only - never -r the whole file on Windows: playwright pins
REM greenlet==3.0.3 (no cp313 Windows wheel -> MSVC source-build failure, seen
REM on the first PIN-1 attempt 2026-08-23). The crawler runs only in the Cloud
REM Run image, so playwright never needs to exist locally. PROJECT_BRAIN #13.
python -m pip install -q fastapi==0.141.1 starlette==1.6.0 pydantic==2.10.4 slowapi==0.1.10
if errorlevel 1 ( echo *** pip install failed - env not aligned, not shipping. & exit /b 1 )
python -c "import fastapi; assert fastapi.__version__=='0.141.1', fastapi.__version__"
if errorlevel 1 ( echo *** local fastapi is not 0.141.1 after install - investigate before shipping. & exit /b 1 )
echo   Local env matches the pins.

echo [3/7] Stamping the release...
call _release_stamp.bat "ship_pin_webstack.bat" "PIN-1: pin fastapi/starlette/pydantic/slowapi as a set - local can no longer drift from the CI-proven window (2026-08-23 422 incident)"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_pin_webstack.bat" "backend/requirements.txt" "docs/PROJECT_BRAIN.md"

echo [4/7] Staging THIS SLICE ONLY...
git add %FILES%
if errorlevel 1 goto :failstamp
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [5/7] Backend tests on the pinned env (the whole point of the slice)...
pushd backend
python -m pytest tests -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [6/7] Committing as release !RELEASE!...
git commit -m "build(deps): PIN-1 - pin the web stack as a set (!RELEASE!)" -m "fastapi==0.141.1, starlette==1.6.0 (now explicit), pydantic==2.10.4, slowapi==0.1.10. The 2026-08-23 incident: '>=' ranges let local keep fastapi 0.115.x while CI resolved newer - 0.115.x cannot resolve PEP-563 string annotations through slowapi's @limiter.limit wrapper, so body models became query params and 9 tests failed 422 locally while CI stayed green. Same lesson as the playwright==1.44.0 pin: local and CI must install the same proven window. Fresh-venv install + full suite (331 passed) verified on exactly these versions in sandbox before shipping. Bump all four together, tests green first. Also records PROJECT_BRAIN lesson 13 from the first ship attempt: never pip install -r wholesale on the Windows box - playwright pins greenlet==3.0.3 (no cp313 Windows wheel, MSVC source-build failure); align via the named pins instead, playwright lives only in the Cloud Run image." -m "Release: !RELEASE!" -m "Ship-Bat: ship_pin_webstack.bat"
if errorlevel 1 goto :failstamp

echo [7/7] Verify committed content matches disk (normalization-aware), then push...
if exist "%TEMP%\shipdiff.txt" del /f /q "%TEMP%\shipdiff.txt"
for %%F in (%FILES%) do (
    git diff --quiet HEAD -- %%F
    if errorlevel 1 ( echo   CONTENT DRIFT: %%~F &echo %%~F>> "%TEMP%\shipdiff.txt" )
)
if exist "%TEMP%\shipdiff.txt" goto :verifyfail
echo   All committed files match disk.
git push origin main
if errorlevel 1 goto :errpush

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!.   HEAD:
git rev-parse --short HEAD
echo  Watch the "Deploy Backend" run - it is the
echo  authoritative gate for these pins on the
echo  Docker/Cloud Run python. After GREEN, /api/health
echo  shows release !RELEASE!.
echo ==================================================
goto :eof

:gitfail
echo *** git HEAD unreadable - repo problem, not shipping. ***
exit /b 1
:stampfail
echo *** Release stamp failed - nothing committed. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:nothingfail
echo *** Nothing staged - index problem. Rolling the stamp back. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:testfail
echo *** TESTS FAILED on the pinned env - not committing. Rolling the stamp back. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:failstamp
echo *** COMMIT/STAGE FAILED - rolling back the release stamp. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:verifyfail
echo *** Committed content differs from disk for the files above - NOT pushing. ***
echo *** Likely NTFS truncation at stage time. Re-copy those files and re-run. ***
exit /b 1
:errpush
echo *** PUSH FAILED (network/creds). Commit is made; run: git push origin main ***
exit /b 1
