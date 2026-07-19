@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == RELEASE STAMPING: a record that writes itself ===========================
REM THE PROBLEM. You run ship bats without always reporting it, and prod carried a
REM broken OAuth endpoint for two pushes because a hand-written FILES list omitted a
REM file. Both are the same failure: a record that depends on a human remembering.
REM
REM THE FIX. The record becomes a BYPRODUCT of shipping, so it cannot be forgotten:
REM   VERSION            single source of truth, MAJOR.MINOR (01.X).
REM   _release_stamp.bat every ship bat calls it; bumps VERSION, appends a row to
REM                      RELEASES.md, hands back %RELEASE% for the commit trailer.
REM   RELEASES.md        append-only table: release, date, WHICH BAT, what changed.
REM   /health            exposes "release" next to the commit SHA. Two ids on purpose:
REM                      the release is what a city can read aloud, the SHA is unique.
REM   Settings UI        shows Release 01.X in large type above the two build SHAs,
REM                      AND warns when frontend and backend releases disagree - they
REM                      deploy as separate CI jobs, so one can go red alone.
REM
REM SELF-DEMONSTRATING: this bat stamps ITSELF, so if the mechanism is broken you find
REM out on the very first use rather than three releases later.
REM
REM WHAT THIS DOES NOT DO. It records what was PUSHED, not what is RUNNING. If CI goes
REM red after a green push, RELEASES.md says 01.1 while Cloud Run still serves 01.0.
REM The Settings panel reads the live backend and is the authority. That is exactly why
REM the mismatch banner exists.
REM
REM NOT BACKFILLED. Earlier releases were shipped unstamped and mapping old commits to
REM bats would be guesswork. 01.0 means "state of prod when stamping was introduced",
REM not "the first release". Use git log for anything before it.

echo [0/7] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Stamping the release...
call _release_stamp.bat "ship_release_versioning.bat" "Introduce release stamping: VERSION, RELEASES.md, /health release, Settings display"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "_release_stamp.bat" "ship_release_versioning.bat" "backend/api/routes/health.py" "backend/tests/test_release_stamp.py" ".github/workflows/deploy.yml" ".github/workflows/deploy_frontend.yml" "frontend/src/views/SettingsView.vue"

echo [2/7] Staging...
git add %FILES%
if errorlevel 1 goto :fail
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [3/7] Untracked-source guard...
set ORPHAN=0
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &set ORPHAN=1 )
)
if "!ORPHAN!"=="1" goto :orphanfail
echo   No untracked source files outstanding.

echo [4/7] Backend tests...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [5/7] Committing as release !RELEASE!...
git commit -m "build: release stamping - the deploy record now writes itself (!RELEASE!)" -m "Two recent failures shared one cause: a record that depended on a human remembering. Ship bats are run without always being reported, and the OAuth endpoint sat broken in production across two pushes because a hand-written file list omitted a module that was never committed. This makes the record a byproduct of shipping instead of a separate step. VERSION holds a single MAJOR.MINOR number; _release_stamp.bat is called by every ship bat and bumps it, appends a row to the append-only RELEASES.md naming the date, the bat and the change, and hands the number back for the commit trailer, so the log and the code are always committed together and cannot disagree. The number is carried through CI into both halves - deploy.yml injects APP_RELEASE into the Cloud Run env and deploy_frontend.yml reads VERSION into VITE_RELEASE - and surfaced on Settings above the two build SHAs. Two identifiers are kept deliberately: the release is short enough for a pilot city to read off their screen on a support call, the commit SHA is unique and cannot be faked by forgetting to stamp. Settings also warns when the frontend and backend releases disagree, because they deploy as separate CI jobs and one can go red alone, which is precisely how a half-deployed dashboard ends up looking healthy. Note the mechanism records what was PUSHED, not what is RUNNING; the Settings panel reads the live backend and remains the authority. Earlier releases are not backfilled because mapping old commits to bats would be guesswork, so 01.0 means the state of production when stamping was introduced rather than the first release. This bat stamps itself, so a broken mechanism surfaces on first use." -m "Release: !RELEASE!" -m "Ship-Bat: ship_release_versioning.bat"
if errorlevel 1 goto :fail

echo [6/7] Blob-verify every committed file (NTFS truncation guard)...
set BAD=0
git show --pretty="" --name-only HEAD > "%TEMP%\relfiles.txt"
for /f "usebackq delims=" %%F in ("%TEMP%\relfiles.txt") do (
    git show HEAD:%%F > "%TEMP%\b.tmp" 2>nul
    fc /b "%TEMP%\b.tmp" "%%F" >nul 2>&1
    if errorlevel 1 ( echo   MISMATCH %%F &set BAD=1 )
)
if "!BAD!"=="1" goto :blobfail
echo   All committed files verified byte-for-byte.

echo [7/7] Push (CI deploys both halves)...
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo  Confirm the mechanism worked - once - by opening
echo  Settings and checking it reads:  Release !RELEASE!
echo  If it still shows the old number, CI has not
echo  finished or a job went red. Do not assume.
echo.
echo  From now on, every ship bat should start with:
echo    call _release_stamp.bat "ship_x.bat" "summary"
echo  and carry VERSION + RELEASES.md in its FILES.
echo ==================================================
goto :eof

:gitfail
echo *** git HEAD unreadable. ***
exit /b 1
:stampfail
echo *** Release stamp failed - VERSION not bumped, nothing committed. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:nothingfail
echo *** Nothing staged - index problem. Rolling the stamp back. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:orphanfail
echo *** The untracked source listed above would be MISSING in prod. ***
echo *** Add it to FILES and re-run. Rolling the stamp back. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:testfail
echo *** TESTS FAILED - not committing. Rolling the stamp back. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:blobfail
echo *** BLOB MISMATCH - truncated. Rolling back the commit. ***
git reset --soft HEAD~1
echo DO NOT PUSH.
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
