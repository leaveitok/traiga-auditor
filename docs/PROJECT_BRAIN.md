# TRAIGA Auditor — Project Brain

> **Portable, tool-agnostic snapshot of what this product is, how it's built, how it
> ships, and every hard-won lesson.** Keep this in the repo. If you switch machines,
> plans, or AI tools, hand this file over first — it rebuilds the full context.
>
> Last updated: 2026-07-12. Owner: Chris Lee, CIO, City of Lewisville · TAGITM Affiliate Director.

---

## 1. What it is (the one-paragraph pitch)

TRAIGA Auditor is a **GRC (governance, risk & compliance) platform for organizations that
*consume* AI** — vendor chatbots embedded in public websites, AI bought through
procurement, and staff LLM use — **not** for organizations that build AI. Beachhead:
Texas municipalities newly regulated under **HB 149 / TRAIGA (Tex. Bus. & Com. Code
Ch. 552, effective Jan 1, 2026)**. Distribution: the **TAGITM** network (~1,200 Texas
municipalities). It's live in production, scanning real cities today.

**The moat:** *discovery-fed compliance.* It **discovers** the AI a government already runs
(outside-in scanner + inside-out Sentinel DLP + procurement + council agendas), **judges**
it against statute, and **generates the legal artifacts** (§552.103 CID response,
§552.104 cure statement, §552.105 Safe Harbor) from live evidence — something document-
template competitors (OneTrust, Credo, Trustible, IBM watsonx.governance) can't do because
they don't have the discovery layer beneath them. The demo *is* the product: scan a
prospect's own site before the meeting and show them AI they didn't know they had.

**Current honest rating: 8/10.** Engineering/product maturity is at its ceiling for the
stage (validated moat, production-grade CI/CD, fail-secure design). What caps it is purely
commercial: pre-revenue, no second agency live unassisted, no pricing. No more code raises
the number — the next point comes from the market.

---

## 2. Coordinates (memorize these)

| Thing | Value |
|---|---|
| Live app | https://traiga-auditor.web.app |
| Backend | Cloud Run `ai-transparency-auditor-api`, region us-central1 |
| Cloud Run URL | https://ai-transparency-auditor-api-otass6vk6a-uc.a.run.app |
| GCP / Firebase project | `traiga-auditor` |
| Firestore DBs | `(default)` = governance, `traiga-sentinel` = DLP telemetry |
| Repo | github.com/leaveitok/traiga-auditor (branch `main`) |
| Runtime service account | `155476092485-compute@developer.gserviceaccount.com` |
| CI deploy service account | `github-actions-deployer@traiga-auditor.iam.gserviceaccount.com` (behind the `GCP_SA_KEY` secret) |
| Local repo root | `C:\Alpha\AI Data Governance Software\AI_Transparency_Auditor_v2` |
| Statute | Texas HB 149 / TRAIGA — Tex. Bus. & Com. Code Ch. 552, effective 2026-01-01 |
| Fingerprint threshold | 0.6 |

Secret Manager secrets: `traiga-service-account`, `traiga-scan-proxy`,
`traiga-sentinel-tokens`, `traiga-scheduler-token`.

---

## 3. Architecture (two-layer, decoupled — non-negotiable)

```
Vue 3 + Vuetify + Pinia (Firebase Hosting)
  Components → Pinia stores → GovernanceService.js → FastAPI /api
                                                        │
FastAPI + Uvicorn (Cloud Run)                           ▼
  thin routes → GovernanceRepository (Protocol)
                 ├── FirestoreRepository  ← production (GOVERNANCE_STORE=firestore)
                 ├── SheetsRepository      ← legacy/rollback
                 └── MockGovernanceRepository ← tests
  engine/ (crawler, fingerprint, validator, cure, scorecard) = STORAGE-AGNOSTIC
```

**Hard rules (from PROJECT_INSTRUCTIONS.md):** components never call axios directly (go
through `GovernanceService`); routes never instantiate a repo (inject via `Depends`);
`engine/` never imports storage; interface-first (Protocol / JSDoc types before impl);
single swap point per layer; governance-first security placeholders; injectable for tests;
`config.py` is env-vars only; cite sources; ask if <95% sure on schema/security changes.

Stack detail: Playwright 1.44.0 (pinned to the Docker base image) + stealth crawler with a
residential-proxy WAF-bypass tier; Firebase Auth ID tokens for the dashboard; separate
device tokens (`X-Sentinel-Token`) for Sentinel ingest. **Governance-as-code:**
`backend/SCHEMA_DEFINITION.json` carries vendor fingerprints, HB 149 rules, Safe Harbor
controls, and the AI_Tool_Catalog — add a vendor/rule/state = a JSON edit + a test, not
engine surgery.

---

## 4. Discovery channels (the moat) + the detection engine

Four channels feed **one** AI-asset registry, each resolving its raw identifier to a
canonical `tool_id` (so the same tool found by multiple channels is one row with a
multi-source evidence trail):

1. **Website scanner** (`discovered_scan`) — Playwright crawl → fingerprint engine.
2. **Sentinel DLP** (`discovered_sentinel`) — browser extension telemetry of staff LLM use.
3. **Procurement** (`discovered_procurement`) — match contract/spend files to the AI catalog.
4. **Council agendas** (`discovered_agenda`) — Legistar API + PDF (pdfminer) + optional
   Vertex/Gemini extraction of award items.

**Fingerprint engine (`engine/fingerprint_engine.py`)** — indicator types:
`script_host_regex`, `iframe_origin_regex`, `dom_selector`, `text_marker_regex`,
`network_request_regex`, `js_global_symbol`, `cookie_name_regex`. A vendor fires when
summed weights ≥ 0.6.

**Vendors as of 2026-07-18 (11):** citibot, civicplus, repd, munibit, granicus,
claude_ai_chatbot, elevenlabs_convai, **frase**, **uneeq**, **unknown_chatbot**,
generic_llm_chat.

**Supporting capture (2026-07-13):** a website scan also records *site metadata* —
agenda platform + client slug, CMS, privacy-policy URL — from
`Site_Metadata_Signatures`, stored as unverified candidates that only fill EMPTY
fields. The Legistar slug an operator actually runs is persisted (verified) as a
backstop, so the Agendas dialog pre-fills it thereafter. Detection is best-effort:
a CivicPlus-fronted city that never links its portal is covered by the backstop.

**Detection gotchas (encoded in the `add-vendor-signature` skill):**
- `dom_selector` matches distinctive **fragments**, not attribute names — the engine drops
  stopwords, so use `citibot`/`frase-iframe`, never bare `class`/`div`/`widget`.
- **Cross-origin chat UIs are unreadable** — the bot lives in a different-origin iframe. Key
  off the PARENT page: iframe `src` origin + loader host, not the widget's greeting text.
- `text_marker_regex` searches both visible text AND HTML (script URLs live in HTML).
- **Fail-secure candidate model:** `unknown_chatbot` (an app-host iframe — amplify/vercel/
  azure/etc. — with a chat/widget token) fires only as `verification_status: candidate_review`,
  never an auto-violation; the pipeline drops it if a branded vendor matched. A candidate-only
  city scores **`review_needed`** (never "clean") — a visible chatbot must never read as 100%.

**Live-confirmed examples:** Odessa "Jett" = Frase (`answers-bot.frase.io`); Midland "Jacky"
= self-hosted on AWS Amplify (structural candidate); Lewisville Citibot; Denton Repd; Grand
Prairie ElevenLabs; Fort Worth via the Deep-Scan WAF escape hatch.

---

## 5. Compliance engine

- **HB 149 rule validation** (`disclosure_validator.py`): presence (§552.051), timing,
  clarity/dark-pattern, privacy-policy reachability, biometric-notice visibility.
- **60-day cure engine** (`cure_period.py`): every failed rule → a violation with citation +
  a cure deadline **anchored to `first_observed_utc`** (never reset on re-scan — verified).
  Statuses: open → in_cure → cured / expired.
  - **UI displays the countdown LIVE** via `frontend/src/utils/cure.js` `liveDaysLeft(cure_deadline_utc)`
    — computed from `deadline − now`, so it ticks down daily and flips to Expired on time,
    regardless of scan cadence. (The old UI showed the stored `days_remaining` snapshot and
    even fabricated the deadline as `today + stored_days` — fixed 2026-07-11.)
- **Scorecard** (`scorecard.py` `build_city_row`): score = 100 − severity-weighted open
  violations; statuses compliant / in_cure / non_compliant / expired / no_ai_detected /
  review_needed / scan_failed / not_assessed. **Fail-secure:** a blocked/failed scan →
  `scan_failed`, never a silent clean; no score shown for unassessed/failed/review-needed.
  Row carries `min_cure_deadline_utc` (earliest open-violation deadline) for live UI math.

**Governance artifacts (generated from live evidence):** AG Response Package (§552.103(b)
item-for-item, .docx), Written Statement of Cure (§552.104, .docx), Safe Harbor Alignment
Statement (§552.105, 14-control NIST AI RMF municipal profile, .docx), council compliance
reports, AI-use policies.

**RBAC** (`core/access.py`, single source of truth): platform_admin (ADMIN_EMAILS bootstrap),
agency_admin (their agency's cities), viewer (read-only). Sentinel DLP reads are
agency-scoped; untagged telemetry is platform-admin-only (fail-secure for monitoring data).

---

## 6. Automated scanning (the scheduler — reliable model)

**Problem solved 2026-07-11:** an in-process APScheduler on Cloud Run with `min-instances=0`
dies when the instance scales to zero, so nightly scans never fired.

**Current model:** **Cloud Scheduler** (managed cron, job `traiga-daily-scan`) POSTs
`/api/audit/scheduled-run` **hourly** with header `X-Scheduler-Token` (secret
`traiga-scheduler-token`, constant-time compare). The endpoint calls
`scheduler.scheduled_scan_due(repo)` — runs only when **SCAN_SCHEDULE_ENABLED** and the
current **UTC hour == SCAN_SCHEDULE_HOUR** and it hasn't already run today — then runs the
scan **off the event loop** (BackgroundTasks → threadpool). Idempotent via `claim_run_slot`
+ a `last_scheduled_date` stamp. The in-process interval remains as a warm-instance backup
that defers to the same due-gate. **UI control:** Settings → "Automated scans" →
`SCAN_SCHEDULE_ENABLED` (on/off) + `SCAN_SCHEDULE_HOUR` (0–23 UTC), auto-rendered.

---

## 7. CI/CD + release mechanics (this is how you ship — internalize it)

**Two independent halves, both gate on green and deploy ONLY committed code:**
- **Backend** — `.github/workflows/deploy.yml`: a `test` job (`pip install -r
  backend/requirements.txt` + `pytest tests/ -q`) then a `deploy` job with `needs: test`.
  A failing test **blocks** the Cloud Run deploy. Deploys on push to `main`.
- **Frontend** — `.github/workflows/deploy_frontend.yml`: `npm ci` → `vite build` (the gate)
  → `firebase deploy --only hosting`. Vite `outDir: '../dist'` (repo-root `dist`, matches
  `firebase.json` `public: dist`). Deploys on push to `main`.

**Local ship pattern (every `ship_*.bat`):** `pytest` gate → `git add` → `git commit` →
**blob-verify** (`fc /b` vs `git show HEAD:<file>`, the NTFS-truncation guard) → `git push`.
The push triggers both CI workflows. See the `ship-it` skill for the canonical template and
the rule to **derive the FILES list from the git diff, never hand-type it**.

**Setup scripts (run once each, in order where noted):**
- `setup_vertex.bat` — enable Vertex AI API + grant runtime SA `roles/aiplatform.user`.
- `setup_firebase_ci.bat` / `finish_frontend_ci.bat` — grant `github-actions-deployer` the
  `roles/firebasehosting.admin` so CI can deploy hosting.
- `setup_scheduler.bat` — enable Cloud Scheduler + Secret Manager, mint the trigger token,
  create the hourly job. **Run BEFORE** `ship_scheduler_cadence.bat` (the deploy references
  the secret it creates).

---

## 8. Known incidents & lessons (read before you touch anything)

1. **NTFS mount truncation (SEVERE, recurring — ~10 files in one session):** writes to the
   mount can truncate a file mid-way. **A truncated file can still COMPILE**: `config.py` cut
   at a statement boundary, passed `py_compile`, and silently dropped `GOVERNANCE_STORE` and
   every `FIRESTORE_*` setting — that would have been a production outage. A clean compile
   proves syntax, never completeness. **Canonical recipe (safe-edit skill):**
   `git show HEAD:file > /tmp/orig` → apply edits in Python with an asserted unique anchor →
   `cp` to the mount → `cmp -s` → compile → check the TAIL and a sentinel symbol near the end
   of the file. Recovery from git only works for TRACKED files — `docs/USER_GUIDE.md`
   truncated and was unrecoverable because it had never been committed (now fixed).
2. **git ↔ prod drift:** `deploy_frontend.bat` (manual) built the whole *working tree*, so a
   fix could go LIVE while staying uncommitted (happened with the audit-log fix). Moving both
   halves to CI (committed-source-only) closed this class. Use the `release-status` skill to
   detect any recurrence.
3. **CI frontend "auth/invalid-api-key":** `frontend/.env` (Firebase web config) is gitignored
   and laptop-only, so the CI build shipped an empty key. Fix: committed
   `frontend/.env.production` (Firebase WEB keys are PUBLIC by design — already in the shipped
   bundle; security is via Auth authorized-domains + Firestore rules). LESSON: any build-time
   env a local build relies on must be given to CI too.
4. **Non-hermetic tests fail in CI:** two Sentinel tests hit a real `SheetsRepository`
   (`service_account.json`, present locally / absent in CI). Fix: the `sclient` fixture
   overrides `get_repository` with a mock. The CI gate *correctly* caught this.
5. **Batch-script traps:** unescaped `(...)` inside an `if (...)` echo throws `.  was
   unexpected at this time.` (use `[brackets]`); every `gcloud`/`npm`/`firebase` (.cmd) call
   needs `call` or the script silently exits 0. **CORRECTION (this file previously said the
   opposite):** inside `( )` blocks use a **PLAIN `&`, never `^&`** — `^&` escapes it to a
   literal character so the `goto`/`set` after it never runs, which produced a FALSE-GREEN
   gate that committed a red build (2026-07-11). `^&` is only for a literal `&` in echo text.
6. **Line-ending warnings** (`LF will be replaced by CRLF`) on commit are harmless.
7. **Git index corruption (2026-07-13):** a stale 0-byte `.git/index.lock` plus an emptied
   index made `git status` report EVERY tracked file as deleted and every working file as
   untracked; `git add` then silently staged nothing. The sandbox cannot unlink the lock
   (NTFS permissions) and the sandbox shares the SAME `.git` as Windows. Every ship `.bat`
   now opens with a self-heal step: drop the stale lock, and if `git ls-files` counts 0,
   delete `.git/index` and `git reset` (rebuilds from HEAD; working tree untouched).
8. **Portal pagination beats you silently (2026-07-13):** Legistar's `/events` returns its
   DEFAULT page — the OLDEST ~1000 events — when no date filter is sent. McKinney (Legistar
   since 2009) therefore returned only 2009–2015, everything was filtered out client-side,
   and the scan reported 0 in under 2 seconds. Fix: filter the window SERVER-SIDE
   (`$filter=EventDate ge datetime'…'`). **Tell: a suspiciously FAST empty result means the
   fetch never reached the data** — not that the gate is wrong (see discovery-triage).
9. **Cloud Run's 300s request cap (2026-07-12):** a 12-month agenda backfill run
   synchronously (one HTTP call per meeting, then one LLM call per item) exceeded
   `--timeout=300` and returned 502. Fixed by making the work fit — concurrent per-meeting
   fetch + one LLM call per meeting — not by raising the ceiling.
10. **Un-pinned framework defaults change your UI (2026-07-18):** the mobile work relied on
   Vuetify's default `display.mobileBreakpoint`, which is `lg` (**1280px**) — so a 1366×768
   laptop or a split-screen window would have silently flipped to the MOBILE layout. Always
   pin a framework default you depend on (`mobileBreakpoint: 'md'` / 960px) and ask "does
   this change the desktop?" before shipping.

---

## 9. Environment / config (names only — secrets never in repo)

Backend env (Cloud Run): `GOVERNANCE_STORE`/`SENTINEL_STORE` (firestore),
`FIRESTORE_PROJECT_ID`, `ADMIN_EMAILS`, `REQUIRE_AUTH=true`, `CORS_ORIGINS`,
`SCAN_PROXY_URL` + `SCAN_PROXY_ONLY_FLAGGED`, `SENTINEL_INGEST_TOKENS`, `SCHEDULER_TOKEN`,
`AGENDA_ENGINE_ENABLED`, `AGENDA_LLM_PROVIDER`/`AGENDA_LLM_MODEL`/`AGENDA_LLM_LOCATION`,
`AGENDA_FETCH_CONCURRENCY`/`AGENDA_LLM_CONCURRENCY` (keep a wide backfill inside the 300s
cap), `AGENDA_LOOKBACK_MONTHS(_MAX)`, `RENDER_TIMEOUT_SECONDS`, `AUDIT_LEASE_STALE_SECONDS`,
`FRAMEWORK_ISO_42001_ENABLED`, `SCAN_SCHEDULE_*`.
Frontend (Vite, PUBLIC, in `.env`/`.env.production`): `VITE_FIREBASE_API_KEY`,
`VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_ADMIN_EMAILS`.

**Agenda LLM (Vertex/Gemini):** model default `gemini-2.5-flash-lite` (GA, supported through
≥2026-10-16); migration path `gemini-3.1-flash-lite`. Model + provider are UI-selectable
(Settings). Auth via the Cloud Run SA (ADC) — no API key. **Pricing verified 2026-07-13:**
2.5 Flash-Lite $0.10/M in, $0.40/M out; it RETIRES **2026-10-16**, after which 3.1 Flash-Lite
is $0.25/$1.50 (2.5×/3.75× more). Cost stays negligible at gated volume (~$0.015 per city
agenda scan) because gating is regex-first and the LLM is batched per meeting.

---

## 10. Prioritized backlog (CIO's list, my recommended order)

Order = **trust/integrity first, then credibility polish, then flagship + growth.**

1. ~~Cure timer live countdown~~ — **DONE** 2026-07-11.
2. ~~Scheduler reliability + UI scan-time~~ — **DONE** 2026-07-11.
3. ~~Audit-log completeness~~ — **DONE** 2026-07-11. Audited all mutating endpoints; coverage
   was already strong (targets/users/agencies/inventory/safe-harbor/CID/reports/discovery/
   settings/scans all log; automated scans log `scan_complete` via `pipeline.py`). Closed the
   two real gaps: destructive `violations_purged` + `scorecard_row_deleted` now audit-logged
   with actor; added `scheduled_scan_triggered`. Test: test_audit_log_coverage.py.
4. ~~Settings-page accuracy~~ — **DONE**. Also DONE since: agenda engine at scale
   (concurrent fetch + per-meeting LLM batching + server-side date window), the in-app
   "which extractor ran" indicator, site-metadata auto-capture + agenda slug pre-fill,
   inventory provenance + deployment badges, curated public-safety AI keywords, the sourced
   `Governance_Profile` (no risk score), and a responsive mobile/tablet UI.
5. **Microsoft/Google OAuth shadow-AI discovery** — THE flagship. Find AI apps employees
   OAuth'd into (Workspace/Entra grants) that IT never approved. Big build, huge value,
   agency differentiator.
6. **Texas cohort sweep (10–20 TAGITM cities)** — grows the signature library (network
   effect) + fills cross-city vendor-prevalence data + *is* the TAGITM pitch scorecard.
7. ~~Dark / stealth mode toggle~~ — **DONE**.
8. **Scoped but NOT built** (design docs only — see `docs/DOC_STATUS.md`): agenda deep-text
   extraction, the adopted-budget channel, bundled vendor-AI-feature detection, and automated
   vendor enrichment. Each has an open-decisions list awaiting a call.

**Path to 9/10 (business, not code):** a second agency operating unassisted + defined
pricing. The sweep (#6) is the concrete on-ramp; pricing/packaging has never been set.

---

## 11. Installed skills (operational muscle memory)

- **add-vendor-signature** — add a fingerprint + pinned regression test (picks up where
  scan-triage ends). The network-effect moat activity.
- **release-status** — read-only drift check: deployed-but-uncommitted, committed-but-unpushed,
  unrun `ship_*.bats`.
- **ship-it** (enhanced) — derive FILES from the git diff + the canonical gated release `.bat`.
- **safe-edit** (updated 2026-07-18) — git-recover → edit in /tmp → `cmp`; and the rule that
  **compiling ≠ intact**.
- **frontend-change** (new) — the production `vite build` CANNOT run in the sandbox (Windows
  binaries in the shared `node_modules`; never `npm install` there); verify with
  `@vue/compiler-sfc` script+template compile. Prefer one global Vuetify default over editing
  N views. Pin framework defaults you depend on.
- **discovery-triage** (new) — why an agenda/procurement/budget run returned 0: fetch →
  window → meeting gate → award gate → extractor → matcher. Sibling of scan-triage (websites).
- Plus: scan-triage, deploy-watch, ci-triage, add-discovery-channel, add-compliance-framework,
  update-user-guide, cloud-setup, compliance-report, schedule, docx/pdf/pptx/xlsx.

---

## 12. How to resume with any tool

Point the tool at: **this file**, then `docs/DOC_STATUS.md` (what is SHIPPED vs DESIGN-ONLY
— read this before believing any design doc), `docs/ARCHITECTURE.md`, `docs/FEATURES.md`,
`docs/OPERATIONS.md`, `docs/ROADMAP.md`, `PROJECT_INSTRUCTIONS.md`, and
`SCHEMA_DEFINITION.json`. That's the full mental model. The code is the source of truth; when
memory and code disagree, trust the code (and update this file). Everything here was true as
of **2026-07-18** — re-verify present-day facts (models, pricing, live scan results) before
asserting them.
