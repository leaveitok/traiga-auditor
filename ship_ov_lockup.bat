@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"
if exist ".git\index.lock" del /f /q ".git\index.lock"

REM Test-env hygiene: a polluted PYTHONPATH (e.g. tests\shims) makes FastAPI
REM resolve BODY models as QUERY params (the 422 class caught 2026-08-23).
REM The gate must test the way CI does - with a clean interpreter path.
set "PYTHONPATH="

REM -- Slice UI-2: OV brand lockup in the nav drawer --------------------------
REM One component, zero behavior change. AppNavDrawer.vue header swaps the
REM generic mdi-shield-star for the OV monogram (inline SVG: currentColor ring
REM adapts to light/stealth, V stays OV Blue) with the "TRAIGA Auditor /
REM OpticVector + GOVERN chip" lockup. Montserrat via the .ov-lockup class
REM shipped in UI-1. Nav items, rail/mobile behavior, profile row untouched.
REM Verified in sandbox: @vue/compiler-sfc parse + compileScript +
REM compileTemplate. The CI vite build (deploy_frontend.yml) is the gate.
REM DEPENDS ON: ship_ov_retheme.bat (UI-1) - run that first ('accent' token
REM and .ov-lockup class come from it).

call _release_stamp.bat "ship_ov_lockup.bat" "UI-2: OV monogram + OpticVector-TRAIGA Auditor lockup with GOVERN chip in the nav drawer"
if errorlevel 1 goto :fail

set FILES="VERSION" "RELEASES.md" "ship_ov_lockup.bat" "frontend/src/components/AppNavDrawer.vue"

echo [1/4] Backend tests (no backend change - regression guard)...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [2/4] Staging + committing...
git add %FILES%
if errorlevel 1 goto :failstamp
git commit -m "feat(ui): Slice UI-2 - OV brand lockup in nav drawer (!RELEASE!)" -m "AppNavDrawer header: OV monogram inline SVG (currentColor ring adapts to theme, V in OV Blue) + TRAIGA Auditor lockup in Montserrat + teal GOVERN module chip per docs/DESIGN_SYSTEM.md (accents mark identity, never actions). No nav-item, rail, mobile, or auth behavior changes. Depends on UI-1 for the accent token and .ov-lockup class." -m "Release: !RELEASE!" -m "Ship-Bat: ship_ov_lockup.bat"
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
echo  After "Deploy Frontend" is GREEN, hard-refresh.
echo  Expect: OV lens+V mark and the OpticVector /
echo  GOVERN lockup at the top of the nav drawer, in
echo  both Light and Stealth themes.
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
