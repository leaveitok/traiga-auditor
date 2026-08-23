@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
if exist ".git\index.lock" del /f /q ".git\index.lock"

REM Test-env hygiene: a polluted PYTHONPATH (e.g. tests\shims) makes FastAPI
REM resolve BODY models as QUERY params (the 422 class caught 2026-08-23).
REM The gate must test the way CI does - with a clean interpreter path.
set "PYTHONPATH="

REM -- Slice UI-1: retheme TRAIGA Auditor to the OpticVector Design System ----
REM Theme/tokens ONLY - zero feature change, zero view-structure change.
REM  * vuetify.js: OV palette (OV Blue #3E9BE0 primary, navy #0F1E2D chrome,
REM    Auditor teal #1F9C8C accent) on BOTH themes; status colors re-toned to
REM    match the GovAssist console exactly (semantics unchanged); VCard default
REM    flips elevation-2 -> flat + hairline border (every card inherits).
REM  * index.html: Montserrat 500/600/700 added to the Google Fonts request;
REM    favicon swapped to the OV monogram (navy lens + white V).
REM  * App.vue: global style - Montserrat for structural type (card/page
REM    titles, .ov-lockup); Roboto stays for body/data.
REM  * docs/DESIGN_SYSTEM.md: NEW - the stamped token sheet + rules + the
REM    cross-repo sync procedure (no runtime dependency between repos).
REM Verified in sandbox: node --check (vuetify.js), @vue/compiler-sfc parse+
REM compile (App.vue), anchors asserted unique. The CI vite build
REM (deploy_frontend.yml) is the authoritative gate.

call _release_stamp.bat "ship_ov_retheme.bat" "UI-1: OpticVector retheme - OV palette both themes, flat hairline cards, Montserrat structural type, OV favicon, docs/DESIGN_SYSTEM.md"
if errorlevel 1 goto :fail

set FILES="VERSION" "RELEASES.md" "ship_ov_retheme.bat" "frontend/src/plugins/vuetify.js" "frontend/index.html" "frontend/src/App.vue" "docs/DESIGN_SYSTEM.md"

echo [1/4] Backend tests (no backend change - regression guard)...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [2/4] Staging + committing...
git add %FILES%
if errorlevel 1 goto :failstamp
git commit -m "feat(ui): Slice UI-1 - OpticVector Design System retheme (!RELEASE!)" -m "Retheme only, zero feature change: OV palette on light + stealth themes (primary OV Blue #3E9BE0, navy #0F1E2D chrome, Auditor teal #1F9C8C module accent), status colors re-toned to match the GovAssist console (semantics unchanged), VCard default flipped to flat + hairline border app-wide, Montserrat for structural type via index.html fonts + one App.vue style block, OV monogram favicon. docs/DESIGN_SYSTEM.md records the shared tokens, the one-accent-per-module rule, and the cross-repo sync procedure. All changes are global-leverage (vuetify.js defaults / tokens / one style block); no view files touched." -m "Release: !RELEASE!" -m "Ship-Bat: ship_ov_retheme.bat"
if errorlevel 1 goto :failstamp

echo [3/4] Blob-verify (NTFS truncation guard)...
set BAD=0
for %%F in (%FILES%) do (
    git show HEAD:%%~F > "%TEMP%\b.tmp" 2>nul
    fc /b "%TEMP%\b.tmp" "%%~F" >nul 2>&1
    if errorlevel 1 ( echo   MISMATCH %%~F &set BAD=1 )
)
if "!BAD!"=="1" goto :blobfail
echo   All blobs verified byte-for-byte.

echo [4/4] Push (CI: vite build + Firebase Hosting)...
git push origin main
if errorlevel 1 goto :errpush

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!.   HEAD:
git rev-parse --short HEAD
echo  After "Deploy Frontend" is GREEN, hard-refresh
echo  the dashboard (Ctrl+Shift+R). Expect: OV blue
echo  buttons, navy-toned stealth, flat hairline cards,
echo  Montserrat titles, OV monogram favicon.
echo  Settings ^> Version ^& Build still shows the same
echo  BACKEND release - this ship is frontend + docs.
echo ==================================================
goto :eof

:testfail
echo *** TESTS FAILED - rolling back the release stamp. Not committing. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:failstamp
echo *** COMMIT/STAGE FAILED - rolling back the release stamp. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:blobfail
echo *** BLOB MISMATCH - a file truncated on disk. Rolling back. ***
git reset --soft HEAD~1
echo DO NOT PUSH. Re-copy the mismatched file and re-run this bat.
exit /b 1
:errpush
echo *** PUSH FAILED (network/creds). Commit is made; run: git push origin main ***
exit /b 1
:fail
echo *** STAMP FAILED (see above). ***
exit /b 1
