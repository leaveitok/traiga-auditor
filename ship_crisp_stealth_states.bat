@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice UI-3c: stealth contrast + neutral city header + loading skeletons --
REM The remaining items from the 2026-08-23 live-app audit (the 8.5 -> 9 slice).
REM  * App.vue: Stealth-only CSS - Vuetify tonal underlay (currentColor at
REM    ~12% activated-opacity, verified against vuetify 3.6 dist CSS) reads as
REM    DISABLED on navy; raised to 0.26 for chips + buttons. Light untouched.
REM  * CityDetailView.vue: hero header drops the tinted band (the app's last
REM    tinted block) - neutral flat card; status color now lives ONLY in the
REM    avatar, status chip, and the score numeral (:class text-bandColor).
REM  * AiInventoryPanel.vue + DashboardView.vue: v-data-table #loading slots
REM    render skeleton rows (same VSkeletonLoader pattern as AnalyticsView);
REM    Dashboard KPI row renders 8 same-footprint skeleton tiles on first load
REM    so the page never jumps. Empty states were already designed - no change.
REM Cosmetic/loading only - zero workflow change, so per update-user-guide the
REM manual is deliberately NOT touched. Zero backend change.
REM Verified in sandbox: @vue/compiler-sfc parse+compile x4; tails checked
REM (App.vue tail change is the appended CSS, by design). CI vite build is the
REM authoritative gate.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_crisp_stealth_states.bat" "UI-3c: stealth tonal-contrast fix, neutral city-detail header (score carries band color), skeleton loading rows + KPI skeleton tiles"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_crisp_stealth_states.bat" "frontend/src/App.vue" "frontend/src/views/CityDetailView.vue" "frontend/src/components/AiInventoryPanel.vue" "frontend/src/views/DashboardView.vue"

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
git commit -m "feat(ui): Slice UI-3c - stealth contrast, neutral city header, skeletons (!RELEASE!)" -m "The 8.5-to-9 slice from the 2026-08-23 live audit. Stealth-only CSS raises Vuetify's tonal underlay from ~12% to 26% so chips and tonal buttons stop reading as disabled on navy (rule verified against vuetify 3.6 dist CSS; Light theme untouched). City Detail drops the last tinted block - the hero band - to a neutral flat card, with status color carried by the avatar, the status chip, and the score numeral via text-bandColor. Both main data tables gain #loading skeleton rows and the Dashboard KPI row renders same-footprint skeleton tiles on first load. Empty states were already designed; unchanged. Cosmetic/loading only - no workflow change, user guide deliberately untouched per update-user-guide. Zero backend change." -m "Release: !RELEASE!" -m "Ship-Bat: ship_crisp_stealth_states.bat"
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
echo  After "Deploy Frontend" is GREEN (allow a few
echo  minutes of CDN propagation), hard-refresh twice.
echo  Expect: readable chips in Stealth, a neutral
echo  City Detail header with the score in band color,
echo  and skeleton rows/tiles during loads.
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
