@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
set "PYTHONPATH="

REM -- Slice UI-3b: consolidated toolbars + flat stat tiles + humanized labels --
REM From the 2026-08-23 Chrome audit of the live app; approach approved by Chris.
REM  * AiInventoryPanel.vue: the four discovery buttons (Sync Staff Usage /
REM    Import Procurement / Agendas / OAuth) collapse into ONE quiet "Add Data"
REM    menu (same permissions, same handlers; old tooltips become subtitles);
REM    Declare AI System becomes the single filled primary; AG Response Pack
REM    goes outlined. KPI strip: flat tiles - numeral carries the color.
REM  * DashboardView.vue: 8 KPI tiles flattened the same way.
REM  * CityDetailView.vue: Compliance Report + AI Use Policy -> outlined primary
REM    (Re-Audit stays the one filled action); Deep Scan flat; raw enum
REM    "unverified_candidate" humanized via verificationLabel().
REM  * User guide v1.7 (md + handout docx + in-app PDF in the SAME commit, per
REM    update-user-guide): the toolbar bullet now describes the Add Data menu.
REM Verified in sandbox: @vue/compiler-sfc parse+compile on all three views;
REM tails diffed identical; PDF grep-proven to contain the new text.
REM Zero backend change. CI vite build is the authoritative gate.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_crisp_toolbars_tiles.bat" "UI-3b: Add Data menu consolidation, flat stat tiles everywhere, outlined city-detail actions, humanized verification labels, user guide v1.7"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_crisp_toolbars_tiles.bat" "frontend/src/components/AiInventoryPanel.vue" "frontend/src/views/CityDetailView.vue" "frontend/src/views/DashboardView.vue" "docs/USER_GUIDE.md" "TRAIGA_Auditor_User_Guide_v1.docx" "frontend/public/TRAIGA_Auditor_User_Guide.pdf"

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
git commit -m "feat(ui): Slice UI-3b - Add Data menu, flat stat tiles, humanized labels (!RELEASE!)" -m "Crisp pass from the 2026-08-23 live-app audit, approach approved by Chris. Inventory toolbar: four discovery buttons consolidated into one quiet Add Data menu (identical permissions and handlers; tooltips became item subtitles) with Declare AI System as the single filled primary. All KPI stat tiles (Dashboard 8, Inventory 4) move from tinted-tonal to flat surface + hairline with the numeral carrying the semantic color, per the approved design canvas. City Detail: Compliance Report and AI Use Policy become outlined primaries so Re-Audit is the one filled action; Deep Scan flat; raw enum unverified_candidate now renders via verificationLabel(). User guide bumped to v1.7 with md + handout docx + in-app PDF regenerated in this same commit (update-user-guide rule). Zero backend change." -m "Release: !RELEASE!" -m "Ship-Bat: ship_crisp_toolbars_tiles.bat"
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
echo  After "Deploy Frontend" is GREEN, hard-refresh.
echo  Expect: one Add Data menu on the Inventory, flat
echo  stat tiles on Dashboard/Inventory/City Detail,
echo  outlined Report/Policy buttons, no raw enum
echo  labels, and the in-app User Guide at v1.7.
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
