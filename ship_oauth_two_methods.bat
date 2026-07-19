@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Two ways in, so endpoint protection cannot block a pilot ================
REM
REM THE PROBLEM. Plenty of municipal shops run EDR, AppLocker, WDAC or Constrained
REM Language Mode that blocks PowerShell outright. Those cities could not run the export
REM script at all, which meant they could not pilot at all.
REM
REM WHAT WE DID NOT DO, DELIBERATELY. A .bat wrapper calling
REM   powershell -ExecutionPolicy Bypass -File script.ps1
REM is the signature move of commodity malware; EDR vendors hunt that exact pattern, so it
REM makes quarantine MORE likely, not less. It also does nothing when the control is
REM AppLocker or WDAC rather than execution policy. Worst of all it asks a security team to
REM weaken a control in order to run a compliance tool - the one argument we cannot afford
REM to lose with a peer CIO. A compiled .exe is worse still: an unsigned binary is more
REM likely to be blocked AND it destroys the "open it and read it" trust model that is the
REM entire pitch.
REM
REM METHOD B - nothing executes on the endpoint. The admin signs into Microsoft Graph
REM        Explorer (Microsoft's own site), runs two documented v1.0 GET queries, and
REM        downloads the JSON:
REM          GET /servicePrincipals?$select=id,appId,displayName,publisherName,signInAudience
REM          GET /oauth2PermissionGrants
REM        engine/collectors/graph_join.py reproduces SERVER-SIDE the join the script does
REM        locally, so both methods converge on identical records before any business logic
REM        runs. Files may be uploaded in either order - each is identified by shape, so an
REM        admin is never asked to label them. The browser parses only enough to reject a
REM        non-JSON file; it never interprets tenant directory data.
REM
REM PAGING IS THE DANGEROUS CASE. Graph Explorer returns ONE page plus @odata.nextLink. An
REM        admin who saves only the first page uploads a truncated tenant, and a truncated
REM        tenant does not error - it reports a short list confidently and the city
REM        concludes they are cleaner than they are. The join detects nextLink and any
REM        grant referencing an app missing from the principals file, and returns
REM        source_warnings that the dialog renders. Never swallowed.
REM
REM THE LIVE DEFECT FIXED. The manual never mentioned Unblock-File. Windows marks any
REM        browser-downloaded file and PowerShell refuses to run marked scripts - and we
REM        INCREASED that exposure last release by making the dashboard the only source.
REM        This would have stopped Euless's admin on his first attempt. Now Step 5, with
REM        the process-scoped execution-policy fallback and an explicit instruction to
REM        switch to Method B rather than disable anything.
REM
REM IN-UI INSTRUCTIONS. The OAuth dialog is now a two-tab walkthrough: role needed, module
REM        install, download + checksum, unblock, run, upload - or the Graph Explorer path -
REM        with a copy button on every command via the new presentational CopyLine.vue. A
REM        mistyped command is indistinguishable from a broken product to the person
REM        running it, and the admin doing this is often not the person who owns the login.
REM
REM PRIVACY. The Graph path counts principalIds and never returns them, with NO opt-in:
REM        the browser route has no legitimate need for identities.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_oauth_two_methods.bat" "Browser-only Graph Explorer path; Unblock-File fix; in-UI step-by-step instructions"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_oauth_two_methods.bat" "backend/engine/collectors/graph_join.py" "backend/api/routes/discovery.py" "backend/tests/test_graph_join.py" "docs/INSTALL_OAUTH_MICROSOFT.md" "docs/USER_GUIDE.md" "docs/DOC_STATUS.md" "frontend/src/components/CopyLine.vue" "frontend/src/components/OAuthImportDialog.vue" "frontend/src/services/types.js"

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
git commit -m "feat(oauth): browser-only Graph Explorer path so endpoint protection cannot block a pilot (!RELEASE!)" -m "Many municipal shops run EDR, AppLocker, WDAC or Constrained Language Mode that blocks PowerShell, which meant those cities could not pilot at all. We deliberately did not solve it with a .bat wrapper calling powershell -ExecutionPolicy Bypass: that is the signature move of commodity malware so it raises rather than lowers the chance of quarantine, it does nothing when the control is AppLocker rather than execution policy, and it asks a security team to weaken a control in order to run a compliance tool. A compiled executable would be worse, since an unsigned binary is more likely to be blocked and destroys the read-the-source trust model the product is sold on. Instead the administrator signs into Microsoft Graph Explorer, runs two documented v1.0 GET queries against servicePrincipals and oauth2PermissionGrants, and uploads the raw JSON, with nothing executing on their endpoint. engine/collectors/graph_join.py reproduces server-side the join the script performs locally so both methods converge on identical records before any business logic runs, files are identified by shape so upload order does not matter, and the browser parses only far enough to reject a non-JSON file rather than interpreting directory data. Paging is handled as the dangerous case it is: Graph Explorer returns one page plus an odata nextLink, and an admin who saves only the first page uploads a truncated tenant which does not error but instead reports a confidently short list, so the join reports nextLink presence and any grant referencing an application missing from the principals file, and the dialog renders those warnings. This release also fixes a live defect the manual carried: it never mentioned Unblock-File, even though Windows marks browser-downloaded files and PowerShell refuses to run marked scripts, an exposure the previous release increased by making the dashboard the only source of the script. That would have stopped the Euless pilot on the first attempt. The OAuth dialog is now a two-tab walkthrough covering role, module install, download and checksum, unblock, run and upload, with a copy button on every command, because a mistyped command is indistinguishable from a broken product and the administrator running this is often not the person who owns the dashboard login. Graph-path principalIds are counted and never returned, with no opt-in." -m "Release: !RELEASE!" -m "Ship-Bat: ship_oauth_two_methods.bat"
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
echo  No shop can now be blocked from piloting:
echo    script if they can, browser if they cannot.
echo.
echo  CONFIRM BEFORE SENDING ANYTHING TO EULESS:
echo   1. Both GitHub Actions runs GREEN
echo   2. Settings shows release !RELEASE!
echo   3. AI Inventory -^> OAuth shows TWO tabs
echo      ("Run the script" / "Browser only")
echo   4. The script tab shows a checksum, and the
echo      browser tab shows both Graph queries
echo.
echo  Send him the dashboard URL + his login +
echo  docs\INSTALL_OAUTH_MICROSOFT.md. Nothing else.
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
echo *** The names are listed above. Fix and amend, or reset --soft HEAD~1. ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
