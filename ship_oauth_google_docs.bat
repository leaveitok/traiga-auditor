@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
if exist ".git\index.lock" del /f /q ".git\index.lock"

REM Documentation catch-up + release stamp for the Google Workspace OAuth channel.
REM (The dialog tab-isolation fix already shipped in commit 027d480.) Moves the user
REM guide md + handout .docx + in-app PDF together per update-user-guide, updates the
REM design docs, and STAMPS the release so the record matches what shipped, per ship-it.

call _release_stamp.bat "ship_oauth_google_docs.bat" "Docs: Google Workspace OAuth channel - user guide v1.6 (md/docx/in-app PDF), DISCOVERY_EXPANSION_DESIGN acquisition, INVENTORY_SPEC discovered_oauth"
if errorlevel 1 goto :fail

set FILES="VERSION" "RELEASES.md" "ship_oauth_google_docs.bat" "docs/USER_GUIDE.md" "TRAIGA_Auditor_User_Guide_v1.docx" "frontend/public/TRAIGA_Auditor_User_Guide.pdf" "docs/DISCOVERY_EXPANSION_DESIGN.md" "docs/INVENTORY_SPEC.md"

echo Staging...
git add %FILES%
if errorlevel 1 goto :failstamp

git commit -m "docs(oauth): Google Workspace channel - user guide v1.6 + design docs (!RELEASE!)" -m "Documentation catch-up for the shipped Google Workspace OAuth import channel. USER_GUIDE.md bumped to v1.6 with the Google Workspace export method; regenerated handout .docx and the in-app PDF (frontend/public/TRAIGA_Auditor_User_Guide.pdf) in the SAME commit so the app never serves a stale guide. DISCOVERY_EXPANSION_DESIGN.md now records the shipped export-based acquisition (Admin console Accessed-apps CSV parsed by engine/collectors/google_oauth.py) instead of the future tokens.list API. INVENTORY_SPEC.md moves discovered_oauth out of future. Release stamped so the log matches what shipped. The dialog tab-isolation fix shipped separately in 027d480." -m "Release: !RELEASE!" -m "Ship-Bat: ship_oauth_google_docs.bat"
if errorlevel 1 goto :failstamp

echo Pushing to origin/main (frontend deploy for the bundled PDF; docs)...
git push origin main
if errorlevel 1 goto :errpush
echo.
echo New release: !RELEASE!   HEAD:
git rev-parse --short HEAD
echo.
echo Note: this bumps the release LOG. The dashboard release number updates on the next
echo BACKEND deploy (this ship is docs + a frontend asset). After the frontend run is
echo GREEN, the in-app User Guide link serves v1.6 (hard-refresh to clear the cache).
goto :eof

:failstamp
echo COMMIT/STAGE FAILED - rolling back the release stamp.
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:fail
echo STAMP FAILED (see above).
exit /b 1
:errpush
echo PUSH FAILED (network/creds). The commit is made; run: git push origin main
exit /b 1
