# System Instructions (Operations Runbook)

Last updated 2026-07-07. How to run, release, and troubleshoot the platform.
Written so a new operator can act without tribal knowledge.

## 1. Daily operation

### Add cities
- One city: Targets page → *Add Target* (set the Cloudflare/WAF flag if known).
- Many cities: Targets → *Bulk Import* (platform admin) → CSV with
  `city,domain[,url,jurisdiction,tags,cloudflare_protected]` → preview →
  import. Imported cities are *Not Assessed* until scanned.

### Run scans
- *Run Audit* (dashboard = all auto-scan cities; city page = that city).
- Scheduler auto-scans every 24h. Cities flagged **WAF-protected are
  excluded** from bulk/scheduled runs — scan them on demand or via Deep Scan.
- Real-time progress shows per city; results persist incrementally.

### Interpret results (honest-status vocabulary)
- `no_ai_detected` — scanned clean against the current signature set.
- `scan_failed` (purple, dashed ring on map) — the crawler was blocked or
  errored. This is an unanswered question, NOT a clean bill. Next step: §3.
- `not_assessed` — never scanned. No score is displayed for either state.
- compliant / in_cure / non_compliant / expired — see the cure clock.

### When a scan finds AI
1. The asset appears in the city's inventory as *Needs attestation*.
2. Attest it: owner, department, purpose, data categories, and the four
   AG-demand answers (training data / outputs / metrics / limitations) —
   the "CID n/8" chip turns green at 8/8.
3. Any disclosure violations start their 60-day cure clocks automatically;
   watch the Cure Deadlines panel.
4. After the city fixes the site, re-scan — cure is verified automatically.

### Discover procured AI from council agendas
Finds AI a city BOUGHT even when it is not on the website. Inventory panel →
*Agendas* (platform/agency admin; requires `AGENDA_ENGINE_ENABLED`).
1. Pick a source: **Legistar** (client slug, e.g. `cityoflewisville`), an **agenda
   PDF URL**, or pasted text. The slug **pre-fills** if a prior run or a website
   scan already learned it — type it once per city, never again.
2. Set the date window (defaults to 12 months). It is applied server-side.
3. Read the result badge: it names **which extractor ran** — *Extracted via Vertex
   (Gemini)* means the AI extractor read every item, so a "0 found" is a
   trustworthy negative; *keyword fallback* means only the simple screen ran.
4. Hits land in the inventory as **Procured · verify** — procured, NOT confirmed
   deployed. They never create a violation or a cure clock. Confirm deployment
   before treating one as a live disclosure obligation.

## 2. Legal document generation (all drafts; counsel review required)

| Document | Where | Statutory basis |
|---|---|---|
| Alignment Statement | City page → Safe Harbor panel | § 552.105(c)–(e) |
| AG Response Package | City page → inventory panel → *AG Response Pack* | § 552.103(b) |
| Written Statement of Cure | City page → Violations card (appears once something is cured) | § 552.104(b)(2) |
| Compliance report / AI Use Policy | City page header buttons | council/remediation |

Safe Harbor readiness: attest the human controls on the city page (name,
timestamp, and notes are recorded and appear in the generated statement).
Machine controls maintain themselves from scan/inventory/cure data.

## 3. WAF-blocked cities (the Deep Scan procedure)

1. Confirm the block: `cmd /c "...\check_city_logs.bat" <domain-fragment>` —
   look for "Possible WAF challenge" / tiny `html_len` / `net_requests=1`.
2. Run Deep Scan: city page → *Deep Scan* → copy the prompt into a Claude
   (Cowork) session with Claude-in-Chrome connected. Claude navigates the
   site as a real browser, extracts evidence, and posts it back
   (`POST /api/audit/chrome-capture`, persist=true).
3. **Immediately flag the city WAF-protected** (city page gear → toggle ON,
   or the shield icon on the Targets page). Otherwise the next nightly scan
   overwrites the verified result with `scan_failed`.

## 4. Sentinel (staff-usage DLP)

- Extension deploys to city devices via MDM (assume users will try Incognito
  or secondary browsers; MDM enforcement is the mitigation).
- Ingest requires `SENTINEL_INGEST_TOKENS` configured; unconfigured ingest
  rejects everything by design.
- Telemetry must carry a **city tag** for the usage sync to attribute it;
  untagged events are skipped fail-secure and reported in the sync summary.
- Merge usage into the registry: Inventory page → *Sync Staff Usage*
  (platform admin). Re-syncs never clobber human-entered fields.
- Watch device heartbeats on the Sentinel view: a silent device may mean a
  disabled extension.

## 5. Release procedure (the ship-it discipline)

Two independent halves — green Actions does NOT mean the UI shipped:
- **Backend** (`backend/`): ships automatically on `git push origin main`
  via GitHub Actions → Cloud Run (~3–5 min).
- **Frontend** (`frontend/`): ships ONLY via `deploy\deploy_frontend.bat`,
  then hard-refresh (Ctrl+F5).

Non-negotiable steps for every release (see `ship_*.bat` files for the
pattern):
1. Tests green first (locally: pytest; sandboxed:
   `PYTHONPATH=backend/tests/shims` + the standalone runner).
2. `git add` explicit files → commit.
3. **Blob-verify every committed file**: `git show HEAD:<file>` vs working
   copy with `fc /b`. Any mismatch → `git reset --soft HEAD~1`, do NOT push.
   (Guards the NTFS silent-truncation failure class — a truncated file can
   still compile and was once committed and crashed production.)
4. Push; deploy frontend if UI changed; verify Actions green AND live
   behavior. Never trust a DONE banner.

Environment quirks (Windows dev machine):
- PowerShell is blocked — everything is `.bat`, run via
  `cmd /c "<full path>.bat"`.
- In any .bat, prefix `gcloud`/`npm`/`firebase` with `call` (they are .cmd
  shims; a bare invocation silently ends the script with exit code 0).
- `git push` only works from the Windows machine.

## 6. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| City shows `scan_failed` | WAF block | §3 procedure |
| City scanned "clean" but you can see a chatbot | Signature gap | scan-triage: pull live DOM, run the fingerprint engine offline, add the vendor signature + regression test (pattern: Denton/repd, Grand Prairie/elevenlabs_convai) |
| Deep Scan result reverted overnight | WAF flag not set | Set the flag (§3 step 3); re-run Deep Scan |
| Dashboard logged out / 401s | Check browser console — every 401 now logs endpoint+time | If recurring: suspect session-affinity to a Playwright-busy instance; durable audit state (H1-2) is the fix |
| Run Audit 500 on fresh instance | per-instance `_audit_state` | Retry; H1-2 removes the class |
| .bat "succeeded" but did nothing | Missing `call` before a .cmd | Fix the .bat; re-run |
| Agenda scan returns 0 / "no items to extract" | Fetch never reached the window (most likely), wrong slug, or a true negative | **discovery-triage** skill. Tell: a *fast* (<2s) empty result means the fetch didn't get there — verify the events query is date-filtered server-side (Legistar returns its OLDEST ~1000 events unfiltered, so a tenant with years of history returns nothing recent) |
| Agenda scan 502s on a wide window | Synchronous run exceeded Cloud Run `--timeout=300` | Make the work fit, don't raise the ceiling: `AGENDA_FETCH_CONCURRENCY`, `AGENDA_LLM_CONCURRENCY` (concurrent fetch + one LLM call per meeting) |
| Result says "keyword fallback" | Vertex unavailable/misconfigured | Extraction still completed but quality dropped — check `AGENDA_LLM_PROVIDER`, the Vertex API enablement and the runtime SA role (cloud-setup) |
| Agenda slug not pre-filling | City has no saved `agenda_client` yet, or detection missed | Expected on sites that don't link their portal — run once with the slug typed; the backstop persists it |
| UI looks squeezed / wrong on a laptop | Mobile breakpoint | Layout switches at **960px** (`display.mobileBreakpoint: 'md'`, pinned in `plugins/vuetify.js`) — below it you get the overlay drawer by design |
| Sheets rollback needed | Firestore incident | Set `GOVERNANCE_STORE=sheets` (+`SENTINEL_STORE`) on Cloud Run; data shape is string-compatible by contract |
| Cloud Run logs | — | `gcloud logging read 'resource.labels.service_name="ai-transparency-auditor-api" AND textPayload:<fragment>'` or `check_city_logs.bat` |

## 7. Access control administration

- Platform admins are bootstrapped by `ADMIN_EMAILS` (Cloud Run env).
- Agencies own cities; create agencies + users in the Admin Console.
  agency_admins manage their own users/cities and attest for their cities;
  viewers get read-only on granted subsets.
- Sentinel telemetry reads are agency-scoped: the platform admin sees all;
  an agency admin/viewer sees only their own cities' events/devices; untagged
  rows are platform-admin-only (fail-secure).

## 8. Testing

- Full local: `cd backend && pytest tests/` (217 passing as of 2026-07-18).
- No-PyPI environments: `PYTHONPATH=backend/tests/shims` + the standalone
  function runner (see any recent session's pattern); 64 tests green as of
  2026-07-07. Six modules require the real FastAPI TestClient and are
  local-only until the CI gate (H1-6) lands.
- **In-app User Guide (keep it from going stale):** the guide is bundled as a static
  asset at `frontend/public/TRAIGA_Auditor_User_Guide.pdf` and linked from the nav
  drawer. Whenever `docs/USER_GUIDE.md` changes, regenerate BOTH deliverables in the
  same commit — the `.docx` at the repo root AND that PDF:
  `pandoc docs/USER_GUIDE.md -o TRAIGA_Auditor_User_Guide_v1.docx --toc --toc-depth=2`
  then convert to PDF and copy it over `frontend/public/TRAIGA_Auditor_User_Guide.pdf`.
  A guide that updates in git but not in the app is worse than no in-app guide.
- Frontend gate: the **CI** Vite build in `deploy_frontend.yml` — this is the only
  place the production frontend build runs. It CANNOT be run from the Linux
  sandbox (the shared `node_modules` holds Windows binaries; never `npm install`
  there — it would break the Windows dev environment). Verify frontend edits by
  script+template compiling the changed SFCs with `@vue/compiler-sfc` (see the
  frontend-change skill), then let CI build.
