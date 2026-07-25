@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Texas SB 1964 government AI code-of-ethics LENS ========================
REM
REM The highest-fit framework extension: SB 1964 (Tex. Gov. Code, 89R 2025) directs DIR to
REM set an AI code of ethics for state agencies AND LOCAL GOVERNMENTS and REQUIRES an AI
REM inventory - the artifact this platform already produces. Its code must align to NIST AI
REM RMF, which is our control spine, so the crosswalk rides the existing mapping.
REM
REM ADDED THE GOVERNANCE-AS-CODE WAY (no engine change - the moat):
REM   SCHEMA    sb1964_ref + sb1964_overlap on all 14 Safe_Harbor controls (9 strong /
REM             5 partial, graded honestly) + a framework-registry entry (TX, mandatory,
REM             default_enabled true - it applies to every TX city). Edited with SAFE-EDIT:
REM             recovered from git, modified in /tmp, copied, verified byte-for-byte, and
REM             re-read from the mount (the schema truncated once this session).
REM   SETTING   FRAMEWORK_SB1964_ENABLED (config default TRUE; SETTABLE switch).
REM   LENS      the readiness panel and the /safeharbor readiness route are ALREADY
REM             framework-generic - SB 1964 appears automatically because its ref resolves
REM             on the controls. Zero code needed for the interactive lens.
REM   REPORT    the Alignment Statement docx is now framework-parameterized
REM             (?framework=sb1964): titled for the framework, cites the statute, shows
REM             each control's SB 1964 dimension + overlap. Defaults to NIST (unchanged).
REM             The panel threads the selected lens through the download.
REM
REM PROVEN: evaluate_profile returns the SAME 14-control result (the lens is a projection,
REM   not a second assessment - the skill's core non-negotiable). 6 lens tests pass; the
REM   docx-variant test runs in CI (needs fastapi). Vue SFCs compiled.
REM
REM CAVEATS carried in the registry + report: dimension-level mapping (DIR rulemaking
REM   pending); data-privacy/fairness only partial; design aid, not legal advice, counsel
REM   review required.
REM
REM SHIP ORDER NOTE: this ship commits a NEW test file. If you have NOT yet run
REM   ship_hardening_and_citation.bat, run THIS one FIRST (so that new test is committed);
REM   otherwise that bat's untracked-source guard will correctly refuse. If you already ran
REM   it, just run this.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_sb1964_lens.bat" "SB 1964 government AI code-of-ethics lens: 14-control crosswalk, setting, framework-parameterized Alignment Statement (no engine change)"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_sb1964_lens.bat" "backend/SCHEMA_DEFINITION.json" "backend/core/config.py" "backend/core/settings.py" "backend/api/routes/safeharbor.py" "backend/tests/test_sb1964_framework.py" "frontend/src/services/GovernanceService.js" "frontend/src/stores/safeharbor.js" "frontend/src/components/SafeHarborPanel.vue" "docs/SB1964_FRAMEWORK_DESIGN.md" "docs/DOC_STATUS.md"

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
git commit -m "feat(safeharbor): Texas SB 1964 government AI code-of-ethics lens (!RELEASE!)" -m "Adds the highest-fit framework extension the governance-as-code way, with no engine change. SB 1964 (Tex. Gov. Code, 89R 2025) directs DIR to establish an AI code of ethics for state agencies and local governments and requires an AI inventory - the artifact this platform produces - and its code must align to the NIST AI RMF, which is the control spine, so the crosswalk rides the existing mapping. Each of the 14 Safe-Harbor controls gains an sb1964_ref and an honestly graded sb1964_overlap (nine strong, five partial - the inventory control maps strongest because SB 1964 mandates the inventory), and a framework-registry entry marks it Texas, mandatory, and enabled by default because it applies to every Texas city. The schema was edited with the safe-edit discipline - recovered from git, modified in tmp, copied, verified byte-for-byte and re-read from the mount - because it truncated once earlier this session. A FRAMEWORK_SB1964_ENABLED setting is added, defaulting on. The readiness panel and route are already framework-generic, so the interactive lens appears automatically once the ref resolves on the controls; the Alignment Statement docx is now parameterized by an optional framework query param, titled for the framework, citing the statute and showing each control's SB 1964 dimension and overlap, defaulting to the unchanged NIST variant, with the panel threading the selected lens through the download. evaluate_profile returns the same fourteen-control result, proving the lens is a projection rather than a second assessment. Caveats travel in the registry and the report: the mapping is dimension-level pending DIR rulemaking, data-privacy and fairness are only partially covered, and it is a design aid requiring counsel review, not legal advice. Six lens tests pass; the docx-variant test runs in CI." -m "Release: !RELEASE!" -m "Ship-Bat: ship_sb1964_lens.bat"
if errorlevel 1 goto :fail

echo [6/6] Verify commit matches disk, then push...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo   1. Watch BOTH Actions runs GREEN (Validate env.yaml
echo      step passes) and Settings shows !RELEASE!.
echo   2. Open a Texas city -^> Safe Harbor panel: the
echo      "Framework lens" selector now offers Texas SB 1964.
echo   3. Pick it, download the Alignment Statement: it is
echo      titled for SB 1964, cites the statute, and shows
echo      each control's SB 1964 dimension + overlap.
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
