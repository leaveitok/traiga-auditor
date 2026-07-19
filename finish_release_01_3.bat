@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Finish release 01.3 - amend in the scoped guard, then push ==============
REM
REM WHAT HAPPENED. ship_oauth_script_delivery.bat did everything right: 276 tests green,
REM commit 1405b72 created. Then its own new guard blocked the push - correctly refusing
REM to ship, but for the WRONG REASON. The guard ran `git diff HEAD` across the entire
REM working tree and tripped on update-user-guide.skill, a file modified hours earlier
REM that is not part of the commit at all.
REM
REM Nothing is broken. The commit is intact locally and was never pushed. This bat fixes
REM the guard's scope, folds that fix into the SAME commit, and pushes.
REM
REM NO NEW RELEASE NUMBER. This is a correction to the tooling that shipped 01.3, not a
REM separate change, so it amends rather than stamping 01.4. VERSION and RELEASES.md stay
REM as committed. Amending is safe here precisely because nothing was ever pushed.
REM
REM THE FIX. _verify_commit.bat now iterates ONLY the paths in HEAD instead of diffing the
REM whole tree, and records failures in a marker FILE rather than a variable. A guard that
REM fires on unrelated dirt is a guard people learn to ignore - worse than no guard.

echo [0/5] Sanity: is there an unpushed commit to finish?
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git log origin/main..HEAD --oneline ^| find /c /v ""') do set AHEAD=%%C
if "!AHEAD!"=="0" goto :nothingtodo
echo   !AHEAD! unpushed commit^(s^) - proceeding.
git --no-pager log origin/main..HEAD --oneline

echo.
echo [1/5] Staging the scoped guard...
git add "_verify_commit.bat" "finish_release_01_3.bat"
if errorlevel 1 goto :fail

echo [2/5] Backend tests (the amended commit must still be green)...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [3/5] Amending release 01.3 (message and release number unchanged)...
git commit --amend --no-edit
if errorlevel 1 goto :fail

echo [4/5] Verifying with the SCOPED guard...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail

echo [5/5] Pushing...
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED release 01.3.
echo.
echo  TO ANSWER THE QUESTION: yes - running a ship bat
echo  IS how the application gets updated. It commits,
echo  pushes, and CI deploys both halves. The guard
echo  stopping you was the system working; it just had
echo  too wide a net.
echo.
echo  CONFIRM BEFORE TELLING EULESS IT IS READY:
echo   1. Both GitHub Actions runs are GREEN
echo   2. Settings shows release 01.3
echo   3. AI Inventory -^> OAuth shows a Download button
echo      and a 64-character SHA-256
echo.
echo  HOUSEKEEPING: update-user-guide.skill has been
echo  modified for a while and is unrelated to any of
echo  this. To clear it:  git checkout -- update-user-guide.skill
echo ==================================================
goto :eof

:gitfail
echo *** git HEAD unreadable. ***
exit /b 1
:nothingtodo
echo.
echo *** Nothing to push - HEAD already matches origin/main. ***
echo *** Release 01.3 may have gone out already. Check:  git log --oneline -3 ***
exit /b 1
:testfail
echo *** TESTS FAILED - commit not amended, nothing pushed. ***
exit /b 1
:verifyfail
echo *** Committed files still differ from disk - NOT pushing. ***
echo *** The names are listed above; that is a REAL mismatch this time. ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
