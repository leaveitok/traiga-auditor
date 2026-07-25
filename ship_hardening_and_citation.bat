@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Deploy hardening + TRAIGA/HB 149 citation naming =======================
REM
REM FIX 1 - WORKFLOW HARDENING (prevents the bug that froze the backend for 6 releases):
REM   deploy.yml now QUOTES EVERY value written into deploy/env.yaml, so YAML can never
REM   coerce one (01.6->float, 24->int, true->bool) into a value gcloud rejects. A new
REM   "Validate env.yaml" step fails the run LOUDLY (with the offending line) if any value
REM   is ever left unquoted again - so this class can never silently reach Cloud Run. The
REM   guard regex and the quoted block were both simulated in a CI-equivalent shell: the
REM   guard passes on the quoted block, catches an unquoted value, and every value parses
REM   as a string.
REM
REM FIX 2 - CITATION NAMING: findings showed only "Tex. Bus. & Com. Code 552.05x", which is
REM   the correct CODIFIED cite but opaque to a council member or AG reviewer. HB 149
REM   (TRAIGA) was codified as Ch. 552, so a pure display helper (engine/reporting/
REM   bundle_spec.cite) now prefixes Ch.-552 citations with "TRAIGA (HB 149) - ...". All
REM   three renderers pick it up (they read the same model). Idempotent (never double-
REM   labels) and leaves non-TRAIGA statutes untouched - which is deliberate headroom for
REM   the SB 1964 Government-Code lens coming next. Two regression tests added.
REM
REM No frontend change. 17 bundle tests pass locally (the harness note aside).

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_hardening_and_citation.bat" "Quote all env.yaml values + validate step (deploy hardening); name TRAIGA/HB 149 on findings"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_hardening_and_citation.bat" ".github/workflows/deploy.yml" "backend/engine/reporting/bundle_spec.py" "backend/tests/test_evidence_bundles.py"

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
git commit -m "fix(ci+reports): quote all env.yaml values with a validate guard; name TRAIGA/HB 149 on findings (!RELEASE!)" -m "Hardens the deploy against the class that froze the backend for six releases: deploy.yml now quotes every value written into the gcloud env-vars file so YAML cannot coerce one into a non-string gcloud rejects, and a new validate step fails the run with the offending line if any value is ever left unquoted, so the bug can never silently reach Cloud Run again. The guard regex and the quoted block were both checked in a CI-equivalent shell - the guard passes on the quoted block, catches an unquoted value, and every value parses as a string. Separately, evidence-bundle findings previously showed only the codified Tex. Bus. & Com. Code section, which is correct but opaque to a council member or Attorney General reviewer; a pure display helper now prefixes Chapter 552 citations with the recognisable TRAIGA (HB 149) name, applied to findings and the statutory reference, idempotent so it never double-labels and leaving non-TRAIGA statutes untouched as deliberate headroom for the SB 1964 Government-Code lens. Two regression tests added." -m "Release: !RELEASE!" -m "Ship-Bat: ship_hardening_and_citation.bat"
if errorlevel 1 goto :fail

echo [6/6] Verify commit matches disk, then push...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo   1. Watch BOTH Actions runs GREEN (the new
echo      "Validate env.yaml" step should pass).
echo   2. Settings shows release !RELEASE!.
echo   3. Reports -^> AG package: findings now read
echo      "TRAIGA (HB 149) - Tex. Bus. & Com. Code ...".
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
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
