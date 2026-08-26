@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

echo [0/7] Git index health...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Pre-flight - edit markers must be present on disk...
findstr /C:"aggregate_by_tool" "backend\engine\collectors\oauth.py" >nul || goto :markerfail
findstr /C:"display_names" "backend\engine\collectors\identity.py" >nul || goto :markerfail
if not exist "backend\engine\applicability.py" goto :markerfail
findstr /C:"assess_asset" "backend\engine\applicability.py" >nul || goto :markerfail
findstr /C:"obligation_basis" "backend\api\routes\inventory.py" >nul || goto :markerfail
findstr /C:"usersTip" "frontend\src\components\AiInventoryPanel.vue" >nul || goto :markerfail
findstr /C:"discovered_oauth" "frontend\src\components\AiInventoryPanel.vue" >nul || goto :markerfail
if not exist "backend\tests\test_obligation_applicability.py" goto :markerfail
findstr /C:"aggregate_by_tool" "docs\PROJECT_BRAIN.md" >nul || goto :markerfail
echo   All edit markers found.

echo [2/7] Stamping the release...
call _release_stamp.bat "ship_inventory_quantity_gate.bat" "Inventory: one row per tool with consent counts, and 552.051 applicability gate"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_inventory_quantity_gate.bat" "backend\engine\collectors\oauth.py" "backend\engine\collectors\identity.py" "backend\engine\applicability.py" "backend\api\routes\inventory.py" "backend\tests\test_oauth_discovery.py" "backend\tests\test_obligation_applicability.py" "frontend\src\components\AiInventoryPanel.vue" "docs\PROJECT_BRAIN.md"

echo [3/7] Staging...
git add %FILES%
if errorlevel 1 goto :fail
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [4/7] Untracked-source guard...
del /f /q "%TEMP%\ov_orphan.txt" 2>nul
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &echo %%F >> "%TEMP%\ov_orphan.txt" )
)
if exist "%TEMP%\ov_orphan.txt" goto :orphanfail
echo   No untracked source files outstanding.

echo [5/7] Backend tests...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [6/7] Committing as release !RELEASE!...
git commit -m "feat(inventory): one row per tool with consent counts + 552.051 applicability gate (!RELEASE!)" -m "Quantity: a tenant holds one OAuth app registration per client ID and a vendor often holds several. merge.py keys ai_assets by city+tool_id, so every grant upserted the same row and the LAST one won: Allen's 249 ChatGPT consents across 4 client IDs displayed as 10, and 63 Claude consents displayed as 'Claude Design (1)'. oauth.aggregate_by_tool now collapses grants in the PURE layer - sums consents, keeps the per-registration breakdown, inherits the worst scope tier, and names the row from the catalog via the new identity display_names map. New Users column plus an App registrations table on row expand." -m "Applicability: inventory.py attached the External Transparency ruleset to every asset, putting 552.051 disclosure duties on staff-side tools an OAuth export found. 552.051 binds an agency that makes an AI system available to interact with consumers. New pure engine/applicability.py gates it, reading EVERY discovery source so an OAuth-first asset later seen live by the crawler is still treated as public-facing. Internal rows now show the applicability note plus the internal governance controls that do apply." -m "UI: discovered_oauth was missing from every frontend provenance map, so shadow AI rendered as 'Declared / Self-declared'. Now badged 'Internal AI scan' + 'Internal use'." -m "Tests: 19 in test_oauth_discovery.py incl. 8 new aggregation/privacy guards; 11 new in test_obligation_applicability.py. PROJECT_BRAIN lesson 14." -m "Release: !RELEASE!" -m "Ship-Bat: ship_inventory_quantity_gate.bat"
if errorlevel 1 goto :fail

echo [7/7] Verify commit matches disk, then push...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail
git push origin main
if errorlevel 1 goto :fail
echo === PUSHED as !RELEASE!. Watch BOTH Actions runs go green, then reload the Allen page. ===
goto :eof

:gitfail
echo *** git HEAD unreadable - repo problem, not shipping. ***
exit /b 1
:markerfail
echo *** An edited file is MISSING its marker - the write did not land. Nothing stamped. ***
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
echo *** Commit does not match disk - NOT pushing. ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
