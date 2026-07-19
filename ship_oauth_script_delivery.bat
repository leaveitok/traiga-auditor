@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Serve the export script FROM THE APP, and fix the commit guard =========
REM
REM THE QUESTION THAT PROMPTED THIS. "Why would I send him a new export script? Is this
REM not in the front end? Where would one get the script in production?" All correct.
REM Emailing a .ps1 means re-sending it after every change, and there was no answer at all
REM for a real customer.
REM
REM MOVED  tools/oauth-export/ -> backend/tools/oauth-export/
REM        NOT cosmetic. CI runs `docker build ./backend`, so the build context is
REM        backend/ and a top-level tools/ directory is NEVER copied into the image. An
REM        endpoint serving from the old path would have worked on a dev machine and
REM        returned 500 in production. A test now asserts the script lives under backend/.
REM
REM WHY THE BACKEND AND NOT A STATIC FRONTEND ASSET. The script PRODUCES the JSON this
REM        service PARSES. The two halves deploy as separate CI jobs, so a frontend-hosted
REM        script could drift ahead of or behind the API that reads its output - the exact
REM        skew the release-mismatch banner exists to warn about. Same deployment = no skew.
REM
REM API    GET /api/discovery/oauth/export-script       (admin) - download, filename
REM                                                      stamped with the release
REM        GET /api/discovery/oauth/export-script/meta  (any authed) - filename, size,
REM                                                      release, SHA-256
REM UI     The OAuth dialog now opens with "Step 1 - Get the export script": a download
REM        button, the checksum, a copy control, and the Get-FileHash command to verify.
REM
REM CHECKSUM DRIFT ELIMINATED. The hash is COMPUTED from the file being served and cached
REM        on (path, mtime, size). docs/INSTALL_OAUTH_MICROSOFT.md no longer carries a
REM        hardcoded SHA-256 - it points at the dashboard. That removes the manual step
REM        that already went wrong once this session, and removes the failure mode where a
REM        city verifies against a stale number and is told their file was tampered with.
REM        A test fails the build if a 64-hex line ever reappears in the manual.
REM
REM COMMIT GUARD FIXED (release 01.2 printed MISMATCH and pushed anyway). New shared
REM        _verify_commit.bat replaces the inline loop. Two defects it fixes:
REM          1. the old loop set BAD=1 inside a for-block and tested it after, so the flag
REM             never survived and the guard COULD NOT BLOCK - decorative in every bat;
REM          2. fc /b byte-compares, but Git for Windows stores LF while the working file
REM             keeps CRLF, so any cmd-written file (VERSION, RELEASES.md) always
REM             "mismatched". git diff understands that normalisation.
REM        Its header states the honest limit: it cannot detect a file that was already
REM        truncated when staged.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_oauth_script_delivery.bat" "Serve the export script from the app with a computed checksum; fix the commit guard"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "_verify_commit.bat" "ship_oauth_script_delivery.bat" "backend/tools/oauth-export/Export-EntraOAuthGrants.ps1" "backend/api/routes/discovery.py" "backend/tests/test_oauth_export_script.py" "docs/INSTALL_OAUTH_MICROSOFT.md" "frontend/src/services/GovernanceService.js" "frontend/src/stores/discovery.js" "frontend/src/components/OAuthImportDialog.vue"

echo [2/6] Staging (including the tools/ -^> backend/tools/ move)...
git add -A tools backend/tools 2>nul
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
git commit -m "feat(oauth): serve the export script from the app, with a computed checksum (!RELEASE!)" -m "Handing a city a PowerShell file by email means re-sending it after every change and leaves no answer to the obvious production question of where the script comes from. It is now downloaded from the dashboard, from the backend rather than as a frontend asset: the script produces the JSON this same service parses, and the two halves deploy as separate CI jobs, so a frontend-hosted copy could drift ahead of or behind the API that reads its output. Serving it from the backend makes that skew impossible. The move from a top-level tools directory into backend/tools was required rather than cosmetic, because CI builds with a context of ./backend and would never have copied the old path into the image - the endpoint would have worked on a developer machine and returned 500 in production, so a test now asserts the script lives inside the build context. The advertised SHA-256 is computed from the file being served and cached on path, mtime and size, and the install manual no longer carries a hardcoded hash; that removes a manual step which had already gone wrong once and removes the failure mode where a city verifies against a stale number and is wrongly told their file was tampered with. A test fails if a 64-hex line reappears in the manual, and another asserts the script still requests only the two Read.All scopes and contains no write cmdlets, so the promise the manual makes to a city IT admin cannot silently lapse. This release also fixes the commit guard, which on 01.2 printed MISMATCH for two files and pushed regardless: it set a flag inside a for-loop block and tested it afterwards, so it could never block, and it byte-compared files that Git for Windows stores with normalised line endings, so cmd-written files always appeared to differ. The replacement is a shared _verify_commit.bat using git's own comparison, and its header records the honest limit that neither form can detect a file already truncated at staging time." -m "Release: !RELEASE!" -m "Ship-Bat: ship_oauth_script_delivery.bat"
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
echo  You no longer send Euless a script. Send him:
echo    1. the dashboard URL and his login
echo    2. docs\INSTALL_OAUTH_MICROSOFT.md
echo  He downloads the script from AI Inventory -^> OAuth,
echo  and the checksum shown there is always the checksum
echo  of the file he just downloaded.
echo.
echo  CONFIRM BEFORE TELLING HIM IT IS READY:
echo    Settings shows release !RELEASE!, then open the
echo    OAuth dialog and check the Download button and a
echo    64-character SHA-256 both appear.
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
echo *** The commit exists locally; fix and amend, or reset --soft HEAD~1. ***
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
