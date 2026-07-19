@echo off
setlocal EnableDelayedExpansion
cd /d "C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2"

REM == OAuth partner harvest: make ONE partner run teach us everything ==========
REM CONTEXT. Euless is piloting as a COLLABORATOR, not a customer. That changes what to
REM optimise for: not polish, but INFORMATION PER RUN. Every round-trip costs days of a
REM peer CIO's goodwill. Previously an app we could not identify only incremented a
REM counter - "skipped: 34" - so his run would have told us we missed things and not
REM which ones.
REM
REM 1. SIGNATURE HARVEST. Unrecognised apps now come back with the app name, publisher,
REM    app ID, scopes and promotability - enough to AUTHOR a catalog signature offline.
REM    This is the network-effect loop: one signature added flags that vendor for every
REM    city afterwards. Opt-in via collect_unmatched, so procurement and agenda payloads
REM    are byte-identical to before. Capped at 200 with an explicit truncation flag, so a
REM    big tenant cannot balloon a response and cannot silently under-report.
REM
REM 2. TWO DROPPED SIGNALS RECOVERED. The export script computed tenant_wide_admin_consent
REM    (an admin consented for the WHOLE org, so no employee individually agreed - the
REM    most serious thing an export can say) and read signInAudience, and every layer
REM    below discarded both. Now carried end to end. signInAudience decides catalog
REM    PROMOTABILITY: a multi-tenant appId means the same thing in every tenant and is
REM    safe to share; an AzureADMyOrg appId is tenant-local and would mis-attribute an
REM    app for every city after it. Fails closed on anything unrecognised.
REM
REM 3. REAL DEFECT FOUND BY THE FIXTURE. Building a realistic Entra fixture immediately
REM    exposed a live bug: "Grammarly for Windows" did NOT match the grammarly catalog
REM    entry. The shared matcher scores Jaccard token overlap, so {grammarly,for,windows}
REM    vs {grammarly} = 0.333, under the 0.5 bar. Entra display names nearly always carry
REM    such qualifiers, so this was the COMMON case, not an edge case.
REM      FIX: also match the PUBLISHER, with legal suffixes stripped ("Grammarly, Inc."
REM      -> "Grammarly"). Confirmed: matched 4 -> 5, and Fireflies rose 0.667 -> 1.0.
REM      REJECTED ALTERNATIVE: awarding a match when alias tokens are contained in the
REM      name. Tested and unsafe - it matches "grok" inside "AI Consulting Services from
REM      Grok Partners LLC" and "claude" inside "Claude Monet Art Archive". Publisher
REM      matching produced zero cross-vendor hits (Adobe scored 0.000 vs grammarly).
REM      The SHARED matcher is untouched, so agenda/procurement carry no regression risk.
REM
REM 4. PS 5.1 ARRAY COLLAPSE. Windows PowerShell 5.1 turns a one-element array into a
REM    bare object, so a tenant with a single consented app would emit "grants": {...}
REM    and the upload would look empty. The script now normalises that case.
REM
REM PRIVACY UNCHANGED. The harvest carries app metadata only. Identities are stripped in
REM the browser AND refused by the pure layer, and the audit log records only a COUNT of
REM unmatched apps - never their names, since it is retained longer and read more widely.
REM
REM CHECKSUM. The .ps1 changed, so docs/INSTALL_OAUTH_MICROSOFT.md carries its NEW
REM SHA-256 (388586446d9c8e2c95c08daf82921c8948655ec57f773152224a71d98bd66b8d). Verified
REM still ZERO write cmdlets and still only the two *.Read.All scopes.

echo [0/7] Git index health (NTFS can wedge it)...
if exist ".git\index.lock" ( echo   removing stale index.lock & del /f /q ".git\index.lock" )
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto :gitfail
for /f %%C in ('git ls-files ^| find /c /v ""') do set TRACKED=%%C
if "!TRACKED!"=="0" ( echo   index reads 0 files - rebuilding from HEAD... & del /f /q ".git\index" 2>nul & git reset -q )

echo [1/7] Stamping the release...
call _release_stamp.bat "ship_oauth_partner_harvest.bat" "OAuth signature harvest; recover tenant-wide + signInAudience; fix qualified-name matching via publisher"
if errorlevel 1 goto :stampfail
if "!RELEASE!"=="" goto :stampfail

set FILES="VERSION" "RELEASES.md" "ship_oauth_partner_harvest.bat" "backend/engine/collectors/oauth.py" "backend/engine/collectors/procurement.py" "backend/core/discovery/oauth_source.py" "backend/api/routes/discovery.py" "backend/tests/test_oauth_signature_harvest.py" "backend/tests/fixtures/entra_export_sample.json" "backend/tests/fixtures/entra_export_single_app.json" "tools/oauth-export/Export-EntraOAuthGrants.ps1" "docs/INSTALL_OAUTH_MICROSOFT.md" "docs/USER_GUIDE.md" "frontend/src/services/types.js" "frontend/src/components/OAuthImportDialog.vue"

echo [2/7] Staging...
git add %FILES%
if errorlevel 1 goto :fail
for /f %%C in ('git diff --cached --name-only ^| find /c /v ""') do set STAGED=%%C
if "!STAGED!"=="0" goto :nothingfail
echo   staged !STAGED! file^(s^).

echo [3/7] Untracked-source guard...
set ORPHAN=0
for /f "usebackq delims=" %%F in (`git ls-files --others --exclude-standard backend frontend/src`) do (
    echo %%F | findstr /r /e "\.py \.vue \.js" >nul 2>&1
    if not errorlevel 1 ( echo   UNTRACKED SOURCE: %%F &set ORPHAN=1 )
)
if "!ORPHAN!"=="1" goto :orphanfail
echo   No untracked source files outstanding.

echo [4/7] Checksum guard - the install manual must match the shipped script...
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 'tools/oauth-export/Export-EntraOAuthGrants.ps1').Hash.ToLower()"`) do set ACTUAL=%%H
findstr /i /c:"!ACTUAL!" "docs\INSTALL_OAUTH_MICROSOFT.md" >nul 2>&1
if errorlevel 1 goto :hashfail
echo   Manual checksum matches the script.

echo [5/7] Backend tests...
pushd backend
python -m pytest tests/ -q
if errorlevel 1 ( popd &goto :testfail )
popd

echo [6/7] Committing as release !RELEASE!...
git commit -m "feat(oauth): harvest unrecognised apps so one partner run grows the catalog (!RELEASE!)" -m "Euless is piloting as a collaborator rather than a customer, so the thing to optimise is information per run, not polish - each round-trip costs days of a peer CIO's time. Previously an application the catalog could not identify only incremented a counter, so his export would have told us we missed things without telling us which. Unrecognised apps now return with the name, publisher, app ID, scopes and promotability needed to author a catalog signature offline, which closes the network-effect loop: one signature added flags that vendor for every city afterwards. It is opt-in through collect_unmatched so procurement and agenda payloads are unchanged, and capped with an explicit truncation flag so a large tenant can neither balloon a response nor silently under-report. Two signals the export script already computed were being discarded by every layer beneath it and are now carried end to end: tenant_wide_admin_consent, where an administrator consented on behalf of the whole organisation so no employee individually agreed, and signInAudience, which decides whether an app ID may be promoted into the catalog shared between cities - multi-tenant IDs are portable, AzureADMyOrg IDs are tenant-local and would mis-attribute an app for every city after them, so promotability fails closed. Building a realistic Entra fixture immediately exposed a live defect: Grammarly for Windows did not match the grammarly entry, because Jaccard token overlap scores it 0.333 against a single-token alias, and Entra display names nearly always carry such qualifiers. Fixed by also matching the publisher with legal suffixes stripped, raising matches from four to five and Fireflies from 0.667 to 1.0. The tempting alternative of awarding a match on token containment was tested and rejected because it matches grok inside an unrelated consulting vendor and claude inside Claude Monet; publisher matching produced no cross-vendor hits. The shared matcher is untouched, so agenda and procurement carry no regression risk. The export script also now normalises PowerShell 5.1's collapse of a one-element array, which would otherwise make a single-app tenant look empty. Privacy is unchanged: the harvest carries app metadata only, identities are stripped in the browser and refused by the pure layer, and the audit log records a count of unmatched apps rather than their names. Twenty-three tests cover the harvest, the recovered signals, promotability, publisher cleaning and the single-app file." -m "Release: !RELEASE!" -m "Ship-Bat: ship_oauth_partner_harvest.bat"
if errorlevel 1 goto :fail

echo [7/7] Blob-verify + push...
set BAD=0
git show --pretty="" --name-only HEAD > "%TEMP%\harvestfiles.txt"
for /f "usebackq delims=" %%F in ("%TEMP%\harvestfiles.txt") do (
    git show HEAD:%%F > "%TEMP%\b.tmp" 2>nul
    fc /b "%TEMP%\b.tmp" "%%F" >nul 2>&1
    if errorlevel 1 ( echo   MISMATCH %%F &set BAD=1 )
)
if "!BAD!"=="1" goto :blobfail
echo   All committed files verified byte-for-byte.
git push origin main
if errorlevel 1 goto :fail

echo.
echo ==================================================
echo  PUSHED as release !RELEASE!
echo.
echo  FOR EULESS - the export script CHANGED, so send him
echo  the current copy and the updated manual together.
echo  The manual's SHA-256 now reads:
echo    !ACTUAL!
echo  If he verifies against an older checksum it will
echo  fail, and that is the guard working correctly.
echo.
echo  Ask him for the "Download for signature review"
echo  file after his dry run. That file is the point of
echo  the whole exercise - it is real Entra naming we
echo  cannot manufacture, and it contains no identities.
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
echo *** Nothing staged - index problem. Rolling the stamp back. ***
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:orphanfail
echo *** The untracked source listed above would be MISSING in prod. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:hashfail
echo *** The install manual's SHA-256 does not match the script being shipped. ***
echo *** A city verifying the checksum would be told the file was tampered with. ***
echo *** Put this hash in docs\INSTALL_OAUTH_MICROSOFT.md:  !ACTUAL! ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:testfail
echo *** TESTS FAILED - not committing. Rolling the stamp back. ***
git reset -q
git checkout -- VERSION RELEASES.md 2>nul
exit /b 1
:blobfail
echo *** BLOB MISMATCH - truncated. Rolling back the commit. ***
git reset --soft HEAD~1
echo DO NOT PUSH.
exit /b 1
:fail
echo *** FAILED - report output. ***
exit /b 1
