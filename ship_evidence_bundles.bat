@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Evidence Bundles - Phase 1 (audience-tailored reports) =================
REM
REM THE GAP THIS CLOSES. Our only visible TRAIGA competitor (TXAIMS) sells one-click
REM audience packages; we had one blended DOCX behind a buried button. This makes us the
REM city's system of record for compliance evidence - the play that stops a city needing
REM a second tool alongside us.
REM
REM ONE ENGINE, NAMED PRESETS. A bundle is sections + optional attachments. "Council
REM Brief" (summary, single PDF) and "AG/Auditor Package" (full, zip + attachments) are
REM the same engine with a different preset. Presets are declared as DATA in
REM SCHEMA_DEFINITION.json (Report_Bundles) - adding an audience is config, not code.
REM
REM ARCHITECTURE (two-layer rules honored):
REM   engine/reporting/bundle_spec.py   PURE: data + preset -> BundleModel. Enforces the
REM                                     two doctrines so no renderer can violate them:
REM                                     PROVENANCE-FIRST (discovered-vs-declared leads) and
REM                                     CANDIDATE-NOT-VERDICT (findings are candidate
REM                                     signals; full presets end with a human attestation).
REM   engine/reporting/render_pdf.py    BundleModel -> PDF (authoritative artifact).
REM   engine/reporting/render_docx.py   BundleModel -> DOCX (editable companion).
REM   core/reporting/bundle_orchestrator.py  pulls repo data (all provenance channels),
REM                                     calls the pure engine, builds the zip package.
REM   api/routes/reports.py             thin: /presets /preview /bundle /package, RBAC +
REM                                     city-scope, audit-logged. Old /generate untouched.
REM   frontend  Reports section: nav + ReportsView (city + preset + LIVE HTML preview +
REM             downloads) + ReportPreview (renders the SAME model the backend renders).
REM
REM TAMPER-EVIDENCE. Every bundle carries a SHA-256 of its own findings (excludes the
REM timestamp, so identical findings hash identically - the Phase 2 stale-detection anchor).
REM Printed in the document and in the package MANIFEST.json.
REM
REM reportlab was added to requirements.txt - the PDF renderer needs it in the image.
REM
REM NOTE: Phase 1 is ON-DEMAND (no persistence). The Evidence-Room history + snapshot
REM storage is Phase 2; the full product-docs refresh is Phase 4. Both are tracked in
REM docs/EVIDENCE_BUNDLES_DESIGN.md and DOC_STATUS.
REM
REM SANDBOX-VERIFIED: 15 bundle tests pass (provenance-first, candidate framing, hash
REM determinism, package manifest integrity, CSV spans all channels). Both documents were
REM rendered and visually confirmed executive-grade. Vue SFCs script+template compiled.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_evidence_bundles.bat" "Evidence Bundles Phase 1: audience presets, PDF+DOCX, package, tamper hash, Reports section"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_evidence_bundles.bat" "backend/SCHEMA_DEFINITION.json" "backend/requirements.txt" "backend/engine/reporting/__init__.py" "backend/engine/reporting/bundle_spec.py" "backend/engine/reporting/render_docx.py" "backend/engine/reporting/render_pdf.py" "backend/core/reporting/__init__.py" "backend/core/reporting/bundle_orchestrator.py" "backend/api/routes/reports.py" "backend/tests/test_evidence_bundles.py" "frontend/src/services/GovernanceService.js" "frontend/src/services/types.js" "frontend/src/stores/reports.js" "frontend/src/components/ReportPreview.vue" "frontend/src/views/ReportsView.vue" "frontend/src/router/index.js" "frontend/src/components/AppNavDrawer.vue" "docs/EVIDENCE_BUNDLES_DESIGN.md" "docs/DOC_STATUS.md"

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
git commit -m "feat(reports): audience-tailored evidence bundles - Phase 1 (!RELEASE!)" -m "Turns one blended report behind a buried button into a Reports section that generates audience-tailored, defensible evidence bundles from a city's live compliance data. A bundle is sections plus optional attachments, so a Council Brief (summary, single PDF) and an AG/Auditor Package (full, zip with inventory CSV, provenance appendix, audit-log excerpt and a manifest) are the same engine with a different preset; presets are declared as data in SCHEMA_DEFINITION.json so a new audience is a config change. The pure engine/reporting/bundle_spec builds a render-agnostic model and enforces the two doctrines centrally: provenance-first, so what was discovered versus declared leads every bundle - the page a self-attestation competitor cannot produce - and candidate-not-verdict, so findings are framed as candidate signals requiring human and legal review, with full presets ending in a human attestation block and a methodology-and-limitations appendix. render_pdf and render_docx walk the same model, the orchestrator assembles data across every provenance channel and builds the zip, and thin routes expose presets, a live-preview model, single-document generation and the package, all city-scoped and audit-logged, leaving the old endpoint untouched. Every bundle carries a SHA-256 of its own findings that excludes the timestamp so identical findings hash identically, printed in the document and the manifest and set up as the Phase 2 stale-detection anchor. The frontend Reports section renders the identical model as an on-brand HTML preview before anything is downloaded. reportlab was added to requirements for the PDF renderer. Phase 1 is on-demand; the Evidence-Room persistence is Phase 2 and the product-docs refresh is Phase 4, both tracked in the design doc. Fifteen bundle tests pass and both documents were visually confirmed executive-grade." -m "Release: !RELEASE!" -m "Ship-Bat: ship_evidence_bundles.bat"
if errorlevel 1 goto :fail

echo [6/6] Verify commit matches disk, then push...
call _verify_commit.bat
if errorlevel 1 goto :verifyfail
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo  Confirm before demoing:
echo   1. Both GitHub Actions runs GREEN
echo   2. Settings shows release !RELEASE!
echo   3. Nav shows "Reports"; pick a city + a preset;
echo      a live preview renders; PDF / DOCX / Package
echo      all download.
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
