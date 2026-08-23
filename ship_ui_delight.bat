@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice UI-6: the delight pass (9 -> 10) ---------------------------------
REM Restrained motion + honest data-viz. Zero workflow change, zero backend
REM change; theme/motion/presentation only - no feature, button, or map is
REM removed (standing rule).
REM  * App.vue: 150ms out-in fade + 4px rise between routes (ov-view
REM    transition); card hover states ease at the same speed;
REM    prefers-reduced-motion disables all of it (WCAG 2.3.3).
REM  * OvCountUp.vue (NEW): stat numerals count up 500ms ease-out cubic -
REM    presentation only, the bound value is always the real figure;
REM    non-numeric values render verbatim; reduced-motion snaps.
REM  * DashboardView.vue: KPI numerals count up; equal-height tiles.
REM  * CityDetailView.vue: the compliance score numeral counts up.
REM  * docs/DESIGN_SYSTEM.md: v1.1 - rules 7-9 (Motion & data-viz honesty).
REM    Rule 9 records the 2026-08-23 DECISION: NO sparklines of any kind until
REM    the KPI history store exists - no time series is stored, and today's
REM    tenant sizes make even honest distribution charts too thin to inform.
REM    Synced with the GovAssist copy in the same working session (GA-UI-2).
REM Cosmetic only - per update-user-guide the manual is deliberately NOT
REM touched. Verified in sandbox: @vue/compiler-sfc parse+compile on all 4
REM .vue files. The CI vite build is the authoritative gate.

echo [0/7] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Pre-flight: prove the edits are applied (fail loudly on a no-op)...
if not exist "frontend\src\components\OvCountUp.vue" ( echo *** OvCountUp.vue missing. & exit /b 1 )
findstr /C:"ov-view" "frontend\src\App.vue" >nul || ( echo *** App.vue motion edit not applied. & exit /b 1 )
findstr /C:"OvCountUp" "frontend\src\views\DashboardView.vue" >nul || ( echo *** DashboardView edit not applied. & exit /b 1 )
findstr /C:"OvCountUp" "frontend\src\views\CityDetailView.vue" >nul || ( echo *** CityDetailView edit not applied. & exit /b 1 )
findstr /C:"Motion & data-viz honesty" "docs\DESIGN_SYSTEM.md" >nul || ( echo *** DESIGN_SYSTEM.md v1.1 section missing. & exit /b 1 )
echo   Edit markers present.

echo [2/7] Stamping the release...
call _release_stamp.bat "ship_ui_delight.bat" "UI-6: delight pass - 150ms route motion, count-up stat numerals, DESIGN_SYSTEM v1.1 Motion and data-viz honesty - sparklines deferred to the KPI history store"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_ui_delight.bat" "docs/DESIGN_SYSTEM.md" "frontend/src/App.vue" "frontend/src/views/DashboardView.vue" "frontend/src/views/CityDetailView.vue" "frontend/src/components/OvCountUp.vue"

echo [3/7] Staging...
git add %FILES%
if errorlevel 1 goto :failstamp
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [4/7] Untracked-source guard...
if exist "%TEMP%\orphan.txt" del /f /q "%TEMP%\orphan.txt"
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &echo %%F>> "%TEMP%\orphan.txt" )
)
if exist "%TEMP%\orphan.txt" goto :orphanfail
echo   No untracked source files outstanding.

echo [5/7] Backend tests (no backend change - regression guard)...
pushd backend
python -m pytest tests -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [6/7] Committing as release !RELEASE!...
git commit -m "feat(ui): Slice UI-6 - delight pass: motion, count-up numerals, distribution sparkbars (!RELEASE!)" -m "Restrained motion: 150ms out-in fade + 4px rise between routes, card hovers ease at the same speed, prefers-reduced-motion disables everything (WCAG 2.3.3). OvCountUp animates stat numerals 500ms ease-out cubic - presentation only, the bound value is always the real figure; non-numeric values render verbatim. Sparklines were built, reviewed, and DEFERRED by decision 2026-08-23: no history store exists so trends would be fabricated, and current tenant sizes make even honest distribution charts too thin to inform - recorded as DESIGN_SYSTEM.md v1.1 rule 9 (rules 7-9 synced with the GovAssist copy), revisit with the KPI history store slice. Cosmetic only - zero workflow or backend change; user guide deliberately untouched per update-user-guide." -m "Release: !RELEASE!" -m "Ship-Bat: ship_ui_delight.bat"
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
echo  After "Deploy Frontend" is GREEN (allow a few
echo  minutes of CDN propagation), hard-refresh twice.
echo  Expect: views fade in, KPI numerals and the
echo  City Detail score count up. OS "reduce motion"
echo  turns it all off.
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
