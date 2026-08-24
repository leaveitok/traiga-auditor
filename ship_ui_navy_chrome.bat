@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice UI-7: navy chrome in BOTH themes ---------------------------------
REM Chris's 2026-08-23 observation: in Light mode the Auditor's drawer went
REM white, so side-by-side with the CivicRoute console (navy rail always) the
REM Auditor read as a generic white admin app - the last brand inconsistency
REM on the platform. DESIGN_SYSTEM rule 1 says navy chrome carries the brand;
REM this slice makes the Light theme honor it. Research grounding (in the DS
REM edit): NN/g contrast-polarity findings (Piepenbrock 2013, Dobres 2017) -
REM light content surfaces win for dense data reading, so the WORKSPACE stays
REM light and the FRAME goes navy. Stealth remains the dark-room demo theme.
REM  * AppNavDrawer.vue: color="navy" + scoped rules tuned to match the
REM    CivicRoute rail (subtitle #7f9bb4, icons #9fc4e6, active white icon on
REM    rgba OV-blue, hairline white dividers). Tonal chips on navy get the
REM    same 0.26 underlay raise as the UI-3c stealth fix; the GOVERN chip
REM    brightens to the dark-surface teal #3FC1AD so it clears the navy.
REM  * App.vue: the MOBILE app bar goes color="navy" to match the drawer.
REM  * docs/DESIGN_SYSTEM.md: rule 1 extended - chrome is navy in both themes;
REM    synced wording ships to the GovAssist copy via ship_ga_ds_navy_sync.bat
REM    in the same working session (two-repo doc sync procedure).
REM Zero behavior change - no feature, button, or map removed (standing rule).
REM Theme choice stays a per-browser preference; only the drawer/app-bar
REM surfaces change. Cosmetic - user guide deliberately NOT touched.
REM Verified in sandbox: @vue/compiler-sfc parse+compile on both .vue files.
REM The CI vite build is the authoritative gate.

echo [0/7] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Pre-flight: prove the edits are applied (fail loudly on a no-op)...
findstr /C:"ov-drawer" "frontend\src\components\AppNavDrawer.vue" >nul || ( echo *** AppNavDrawer edit not applied. & exit /b 1 )
findstr /C:"UI-7: navy chrome" "frontend\src\App.vue" >nul || ( echo *** App.vue app-bar edit not applied. & exit /b 1 )
findstr /C:"UI-7" "docs\DESIGN_SYSTEM.md" >nul || ( echo *** DESIGN_SYSTEM.md rule-1 extension missing. & exit /b 1 )
echo   Edit markers present.

echo [2/7] Stamping the release...
call _release_stamp.bat "ship_ui_navy_chrome.bat" "UI-7: navy chrome in both themes - drawer and mobile app bar stay navy in Light, matching the CivicRoute rail; DESIGN_SYSTEM rule 1 extended with the NN/g grounding"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_ui_navy_chrome.bat" "docs/DESIGN_SYSTEM.md" "frontend/src/App.vue" "frontend/src/components/AppNavDrawer.vue"

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
git commit -m "feat(ui): Slice UI-7 - navy chrome in both themes (!RELEASE!)" -m "The last brand inconsistency on the platform: in Light mode the drawer rendered white, so the Auditor read as a generic admin app next to the CivicRoute console's always-navy rail. DESIGN_SYSTEM rule 1 (navy chrome carries the brand) now applies per-theme: the nav drawer and mobile app bar stay Navy #0F1E2D in Light and Stealth alike, with drawer text/icon/active values matching the CivicRoute rail, the 0.26 tonal-underlay raise from the UI-3c finding applied to chips on navy, and the GOVERN chip brightened to the dark-surface teal. Research grounding recorded in the DS edit: NN/g contrast-polarity findings (Piepenbrock 2013, Dobres 2017) - light content surfaces win for dense data reading, so the workspace stays light and the frame carries the brand; Stealth remains the full-dark option. GovAssist DS copy synced via ship_ga_ds_navy_sync.bat in the same session. Zero behavior change; theme choice stays a per-browser preference." -m "Release: !RELEASE!" -m "Ship-Bat: ship_ui_navy_chrome.bat"
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
echo  Expect: in LIGHT mode the drawer and mobile bar
echo  are navy with white text - matching the console
echo  rail - and content stays light. Stealth unchanged
echo  in character.
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
