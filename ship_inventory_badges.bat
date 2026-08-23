@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice UI-3a: uniform Source-column badges in the AI Inventory ----------
REM Chris flagged the ragged Source column (mixed chip sizes, inline drift) on
REM the live 01.14 app. Fix: the provenance + deployment + not-re-observed
REM chips render as ONE left-aligned flex column, all x-small, 2px rhythm.
REM Zero data/logic change - template block only in AiInventoryPanel.vue.
REM docs/PROJECT_BRAIN.md gains lessons 11 (never template a new bat from an
REM old bat - this bat is built from the ship-it skill's canonical template)
REM and 12 (the fastapi 422 body-as-query env drift class + its fix).
REM Verified in sandbox: @vue/compiler-sfc parse+compileScript+compileTemplate;
REM file tails diffed identical outside the edit region. CI vite build is the
REM authoritative gate.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_inventory_badges.bat" "UI-3a: uniform Source-column badge stack in AI Inventory; PROJECT_BRAIN lessons 11-12 (bat-template provenance, fastapi 422 drift)"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_inventory_badges.bat" "frontend/src/components/AiInventoryPanel.vue" "docs/PROJECT_BRAIN.md"

echo [2/6] Staging...
git add %FILES%
if errorlevel 1 goto :fail
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [3/6] Untracked-source guard...
if exist "%TEMP%\orphan.txt" del /f /q "%TEMP%\orphan.txt"
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &echo %%F>> "%TEMP%\orphan.txt" )
)
if exist "%TEMP%\orphan.txt" goto :orphanfail
echo   No untracked source files outstanding.

echo [4/6] Backend tests (no backend change - regression guard)...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [5/6] Committing as release !RELEASE!...
git commit -m "fix(ui): Slice UI-3a - uniform Source badge stack in AI Inventory (!RELEASE!)" -m "The provenance, deployment, and not-re-observed chips in the Inventory Source column rendered at mixed sizes with inline drift - ragged at table density. They now render as one left-aligned flex column, all x-small tonal chips on a 2px rhythm, per the crisp-pass rule added to the template comment. Tooltips and all data/logic unchanged. PROJECT_BRAIN.md gains lesson 11 - never template a new ship bat from an old bat; start from the ship-it skill's canonical template, which this bat does - and lesson 12, the fastapi body-as-query 422 environment-drift class and its fix." -m "Release: !RELEASE!" -m "Ship-Bat: ship_inventory_badges.bat"
if errorlevel 1 goto :fail

echo [6/6] Verify committed content matches disk (normalization-aware), then push...
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
echo  After "Deploy Frontend" is GREEN, hard-refresh
echo  the AI Inventory. Expect: every Source cell is a
echo  tidy two-line badge stack, same size, same left
echo  edge, in both Light and Stealth themes.
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
echo *** Committed content differs from disk for the files above - NOT pushing. ***
echo *** Likely NTFS truncation at stage time. Re-copy those files and re-run. ***
exit /b 1
:errpush
echo *** PUSH FAILED (network/creds). Commit is made; run: git push origin main ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
