@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == Evidence Bundles - Phase 2 (the Evidence Room) =========================
REM
REM Turns Phase 1's on-demand bundles into a persistent, defensible evidence trail. A
REM saved snapshot FREEZES the render-agnostic BundleModel (small JSON) plus its content
REM hash and a fingerprint of the source data. Any format re-renders from the frozen model
REM on demand, so nothing is lost and no blob store is needed in beta - the ArtifactStore
REM abstraction (design doc) is where prod would ALSO persist rendered bytes to GCS later.
REM
REM   PROTOCOL   save/get_report_snapshots/get/delete added to GovernanceRepository and
REM              implemented in Mock, Sheets (new ReportSnapshots tab), and Firestore
REM              (report_snapshots collection). Delete is a TOMBSTONE - evidence is marked
REM              deleted, never hard-removed, so an auditor can always be shown it existed.
REM   ORCHESTRATOR  create_snapshot freezes the model; list_snapshots computes a live
REM              source fingerprint per city and flags a snapshot STALE when the findings
REM              have changed since; render_snapshot / render_snapshot_package rebuild from
REM              the frozen model (self-contained, hash-verified).
REM   ROUTES     POST/GET /reports/snapshots, GET /{id}/download + /{id}/package,
REM              DELETE /{id} (platform_admin). City-scoped, audit-logged.
REM   FRONTEND   Reports view gains an EVIDENCE ROOM table (saved snapshots with a
REM              Current/Stale chip, integrity hash, PDF/DOCX/Package re-download, and an
REM              admin tombstone with confirm), plus a "Save to Evidence Room" action.
REM
REM   PHASE-1 BUG FIXED HERE: report/package downloads used plain <a href> links, which do
REM   NOT carry the Firebase Bearer token, so they 401 in the deployed app (REQUIRE_AUTH=
REM   true). All report + snapshot downloads now fetch as an AUTHENTICATED blob via axios
REM   and save client-side - the same pattern the original compliance-report download uses.
REM
REM   Snapshot packages rebuild attachments (inventory CSV, provenance appendix) from the
REM   frozen model, so they are fully reproducible; the transient audit-log excerpt is only
REM   in the live on-demand package, by design.
REM
REM   SANDBOX-VERIFIED: 7 snapshot tests pass (Protocol round-trip, hash+fingerprint,
REM   re-render from frozen model, self-contained package w/ matching manifest, stale flips
REM   on data change, tombstone semantics). Phase-1 bundle tests still green. Vue SFCs
REM   compiled; JS parsed.

echo [0/6] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/6] Stamping the release...
call _release_stamp.bat "ship_evidence_room.bat" "Evidence Bundles Phase 2: Evidence Room - immutable snapshots, stale detection, tombstone; auth-safe downloads"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_evidence_room.bat" "backend/core/governance_service.py" "backend/core/config.py" "backend/tests/mock_repository.py" "backend/core/repositories/sheets_repository.py" "backend/core/repositories/firestore_repository.py" "backend/core/reporting/bundle_orchestrator.py" "backend/api/routes/reports.py" "backend/tests/test_evidence_snapshots.py" "frontend/src/services/GovernanceService.js" "frontend/src/stores/reports.js" "frontend/src/views/ReportsView.vue" "docs/DOC_STATUS.md"

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
git commit -m "feat(reports): Evidence Room - immutable, reproducible snapshots (!RELEASE!)" -m "Phase 2 of evidence bundles turns on-demand generation into a persistent evidence trail. A saved snapshot freezes the render-agnostic BundleModel plus its content hash and a fingerprint of the source data it was built from; any format re-renders from the frozen model on demand, so nothing is lost and no blob store is needed in beta - the ArtifactStore abstraction is where production would additionally persist rendered bytes to GCS. The GovernanceRepository Protocol gains save, list, get and delete for snapshots, implemented in the Mock, Sheets (a new ReportSnapshots tab) and Firestore (a report_snapshots collection) backends; delete is a tombstone rather than a hard removal, because evidence should never be destroyable - an auditor can always be shown a record existed. The orchestrator freezes the model on create, computes a live source fingerprint per city to flag a snapshot stale when the findings have changed since it was taken, and re-renders a snapshot or its full package from the frozen model alone, rebuilding the inventory and provenance attachments from that model so a package is self-contained and reproducible. Thin routes expose create, list, per-format download, package and an admin-only tombstone, all city-scoped and audit-logged. The Reports view gains an Evidence Room table showing each saved snapshot with a Current or Stale chip, its integrity hash, PDF/DOCX/package re-download and an admin tombstone with confirmation. This release also fixes a Phase 1 defect: report and package downloads used plain href links that do not carry the Firebase bearer token and therefore 401 in the deployed app where auth is required; every report and snapshot download now fetches as an authenticated blob through axios and saves client-side, matching the original compliance-report pattern. Seven snapshot tests pass alongside the Phase 1 bundle tests." -m "Release: !RELEASE!" -m "Ship-Bat: ship_evidence_room.bat"
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
echo   3. Reports: generate a bundle, click "Save to
echo      Evidence Room"; it appears in the table as
echo      Current with an integrity hash. Re-download
echo      PDF/DOCX/Package from the row.
echo   4. Run an audit for that city, return to Reports:
echo      the saved snapshot now shows STALE.
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
