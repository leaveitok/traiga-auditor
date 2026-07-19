# System Features & Functions

Last updated 2026-07-18. Organized by domain; each feature lists what it does,
where it appears in the UI, and its API surface.

---

## 1. Discovery — finding the AI

### 1.1 External compliance scanner
Crawls each registered city's public website with a real browser engine
(Playwright + stealth), auto-detects WAF challenges, and escalates blocked
crawls through a residential proxy. **Fail-secure:** a blocked or failed crawl
is recorded as `scan_failed` — never silently reported clean.
- UI: *Run Audit* button (dashboard and city pages) with real-time progress.
- API: `POST /api/audit/run` (optional `cities=` filter), `GET /api/audit/run` (status).
- Scheduler: automatic scans every 24h (`GET /api/audit/schedule`); cities
  flagged WAF-protected are excluded from bulk runs (proxy cost control).

### 1.2 Vendor fingerprint engine
Matches crawled pages against weighted signatures in
`backend/SCHEMA_DEFINITION.json` (11 vendors as of 2026-07-18: citibot,
civicplus, repd, munibit, granicus, claude_ai_chatbot, elevenlabs_convai,
frase, uneeq, unknown_chatbot, generic_llm_chat). Indicators span script hosts, iframe origins, DOM
selectors, network requests, and text markers; a vendor fires when summed
weights reach the 0.6 threshold. Signatures are data, not code — new vendors
ship as JSON edits with regression tests.

### 1.3 Deep Scan (WAF escape hatch)
For sites that block datacenter crawlers entirely (e.g. Fort Worth): a real
Chrome session extracts the rendered evidence and posts it to
`POST /api/audit/chrome-capture` (persist=true). The city page shows a *Deep
Scan* button with a copy-paste prompt for a Claude (Cowork) session. Verified
end-to-end on fortworthtexas.gov 2026-07-07.

### 1.4 Sentinel staff-usage discovery (inside-out)
Sentinel browser-DLP telemetry (see 5.1) is merged into the registry:
staff usage of ChatGPT/Claude/Gemini/Copilot becomes inventory rows with
`provenance=discovered_sentinel`, carrying event counts, DLP-blocked counts,
device counts, and triggered policies. Untagged telemetry is skipped
fail-secure, never guessed into a city.
- UI: *Sync Staff Usage* button on the inventory panel (platform admin).
- API: `POST /api/inventory/sync-sentinel`.

### 1.5 Bulk city import
CSV import of audit targets (platform admin only — agencies have no reason to
bulk-import). Client-side parse/preview, server-side validation and dedupe
(domains normalized: scheme/www/path stripped). Imported cities appear as
*Not Assessed*; scanning stays deliberate.
- UI: *Bulk Import* on the Targets page, with downloadable CSV template.
- API: `POST /api/targets/bulk` (2,000-row cap).

### 1.6 Procurement / contract discovery (outside-in, declared-adjacent)
Matches an uploaded vendor / spend / contract file against the canonical AI tool catalog and merges hits into the
registry as `provenance=discovered_procurement`. Matches the **product/line-item**
as well as the vendor company (so "Microsoft → Copilot" resolves), and runs an
AI-keyword screen so a line item that names AI (e.g. "AI permitting assistant")
surfaces as a candidate for review even from an unknown vendor — never dropped.
The AI-keyword list is governance-as-code (27 terms) and includes a curated
public-safety cluster (ALPR / license-plate recognition, gunshot detection,
predictive policing) chosen for PRECISION: broad words like "smart" are
deliberately excluded so the human-review queue stays trustworthy.
- UI: *Import Procurement* on the AI Inventory panel (platform/agency admin).
- API: `POST /api/discovery/procurement` (city-scoped, 5000-row cap).

### 1.7 Cross-channel identity substrate
Every discovery channel (scan, Sentinel, procurement, future OAuth/network/agenda)
resolves its raw identifier to one canonical `tool_id` via governance-as-code
aliases (`SCHEMA_DEFINITION.json` `AI_Tool_Catalog`), so the same tool found by
multiple channels is **one** registry row whose `discovery_sources_json` lists
every source that found it. New channels plug in via the `DiscoveryCollector`
pattern + `COLLECTORS` registry — one collector, one alias block, no downstream
change. See `docs/DISCOVERY_EXPANSION_DESIGN.md` and `docs/AGENDA_ENGINE_DESIGN.md`.

### 1.8 Council-agenda discovery (procured AI, from the public record)
Scans a city's council / EDC meeting agendas for awarded technology contracts and
merges AI hits into the registry as `provenance=discovered_agenda`. Sources:
**Legistar Web API** (by client slug), an **agenda PDF URL** (pdfminer), or pasted
agenda text. Gating is cheapest-first — date window, then meeting type (council/EDC
kept; planning/zoning/advisory skipped), then an award-keyword gate — so only
contract items reach the extractor.
- **Extraction is a single swap point** (`AGENDA_LLM_PROVIDER`): `vertex` (Gemini
  on Vertex AI, structured JSON, enterprise no-train) or `keyword` (no-LLM
  fallback). The result reports **which extractor actually ran** — *Extracted via
  Vertex (Gemini)* vs *keyword fallback* — so a silent fail-open is visible in the
  app without reading cloud logs.
- **Scale:** per-meeting item fetches run on a bounded thread pool and the LLM is
  batched **one call per meeting**, keeping a 12-month backfill inside Cloud Run's
  300s request limit (`AGENDA_FETCH_CONCURRENCY`, `AGENDA_LLM_CONCURRENCY`).
- **The date window is applied server-side** on the portal query. This is required,
  not an optimization: Legistar otherwise returns its oldest ~1000 events, so a
  long-standing tenant's recent window never arrives (verified on McKinney, whose
  Legistar history starts in 2009).
- Writes discovery rows ONLY — never a disclosure violation or a cure clock.
- UI: *Agendas* on the AI Inventory panel. API: `POST /api/discovery/agenda`.

### 1.9 Site-metadata auto-capture (so the operator types less)
A website scan also records what it can observe about the city's stack: agenda
platform + client slug, CMS, and privacy-policy URL — matched from
`Site_Metadata_Signatures` (7 agenda platforms, 7 CMS families) as
governance-as-code. Values are stored as **unverified candidates** and only ever
fill an EMPTY field, so nothing a human confirmed is overwritten.
- **Backstop:** the Legistar slug an operator actually runs is persisted to that
  city (verified), so the Agendas dialog **pre-fills it next time**. Detection is
  best-effort by design — a city whose homepage doesn't link its portal (common on
  CivicPlus sites) is covered by this memory instead.

## 2. Compliance — judging what was found

### 2.1 HB 149 rule validation
Detected assets are evaluated against the External Transparency Module rules:
disclosure presence (§ 552.051), disclosure timing, disclosure clarity /
dark-pattern check, privacy-policy reachability, biometric notice visibility.
Rules are schema data (governance-as-code); adding statutes means adding
modules, not engine code.

### 2.2 Violations & 60-day cure engine
Every failed rule becomes a violation record with severity, statutory
citation, first/last observed, and a 60-day cure deadline (§ 552.104).
Statuses: open → in_cure → cured / expired. Re-scans verify cure
automatically.
- UI: Violations view; per-city violations card; cure-period gauges.
- API: `GET /api/violations` (filterable), `GET /api/violations/{id}`.

### 2.3 Compliance scorecard & statuses
Per-city score (100 minus severity-weighted open violations) and status:
compliant / in_cure / non_compliant / expired / **no_ai_detected** /
**scan_failed** / not_assessed. A failed or never-run scan shows **no score**
("—"), never a default 100.
- API: `GET /api/scorecard`, `GET /api/scorecard/summary`.

### 2.4 Texas compliance map
Dependency-free SVG map of Texas; pins colored by status (scan_failed renders
purple with a dashed ring so it can never be mistaken for "fine"), clickable
through to city pages. Gazetteer covers 116 Texas cities (true lat/lon positions, with
zoom + pan) including the DFW and top-100 sweep cohorts.

### 2.5 Cure-deadline countdown panel
Dashboard panel ranking cities by days remaining on their statutory cure
clocks (worst first, urgency colors). Converts scan results into legal
deadlines — the operational view no generic GRC dashboard has.

## 3. Governance — the registry and the paperwork

### 3.1 AI Use-Case Inventory (discovery-fed registry)
One registry, five provenance channels: `discovered_scan` (public website),
`discovered_agenda` (council agendas), `discovered_procurement` (contract/spend
files), `discovered_sentinel` (staff usage), and `declared` (humans add what none
of them can see). Every row shows **where it was inventoried from** plus a
**deployment badge** derived from provenance — *Live on site* (a real disclosure
obligation now) vs *Procured · verify* / *Budgeted · verify* (found in a record,
not confirmed deployed) — so an implementation-timing gap is never misread as live
non-compliance. Merge contract: scans/syncs refresh machine fields only; human fields
(owner, purpose, attestation, CID answers) are never clobbered. Workflow:
discovered → attested → retired, with annual review dates.
- UI: /inventory (all cities) and embedded per-city panel; attest/declare/retire dialogs.
- API: `GET/POST /api/inventory`, `PATCH /api/inventory/{asset_key}`.
- Spec: [INVENTORY_SPEC.md](INVENTORY_SPEC.md).

### 3.2 TRAIGA Safe Harbor Readiness (Municipal AI Profile)
A 14-control municipal profile of the NIST AI RMF (+ Generative AI Profile,
NIST AI 600-1) supporting the § 552.105(c)–(e) defenses. Eight controls
machine-verify from platform data (scan cadence, inventory coverage,
disclosure testing, cure tracking, audit trail, Sentinel visibility); the
rest are click-to-attest with recorded name/timestamp. Four function rings
(Govern/Map/Measure/Manage) with readiness bands.
- **Alignment Statement** (.docx): the written § 552.105 evidence document —
  every control footnoted to its evidence, counsel-review disclaimer,
  signature block.
- UI: Safe Harbor panel on every city page.
- API: `GET /api/safeharbor/{city}`, `POST /api/safeharbor/{city}/attest`,
  `GET /api/safeharbor/{city}/statement`.

### 3.3 AG Civil Investigative Demand (CID) readiness & response
Pre-computes, per asset, which of the eight § 552.103(b) demandable items are
already answerable — machine-derived, human-attested, or honestly
vendor-referred (a city cannot know a vendor's training data; the referral IS
the answer). Gaps surface as "CID n/8" chips *before* any letter exists; the
four human answers (training data, outputs, metrics, limitations) are edited
in the asset dialog.
- **AG Response Package** (.docx): sections mirror § 552.103(b)(1)–(8)
  item-for-item with per-item evidence sourcing and appendices.
- **Written Statement of Cure** (.docx): structured to § 552.104(b)(2)(i)–(iii)
  from the cured-violations record — producible because the platform tracks
  the cure window operationally.
- API: `GET /api/cid/{city}/readiness`, `GET /api/cid/{city}/package`,
  `GET /api/cid/{city}/cure-statement`.

### 3.4 Compliance reports & AI Use Policy generator
Council-ready TRAIGA compliance report (.docx) per city; vendor-specific AI
Use Policy documents (remediation aid).
- API: `GET /api/reports/generate?city=`, `GET /api/remediation/policy?city=`.

### 3.5 Vendor governance profile (sourced — deliberately not scored)
Per-tool governance context assembled without inventing anything. **Statutory
exposure** is derived deterministically from the observed function to the TRAIGA
rules it implicates (chatbot → § 552.051 disclosure + privacy-policy reachability;
biometric / facial recognition → the biometric provision), which requires no
knowledge of vendor internals. **Documented vendor facts** are recorded only with a
`source_url` and date, and otherwise read `not_published` / `unknown`. Anything
unobservable becomes a human/vendor attestation question.
**No composite risk score is produced** — a number nobody can cross-examine is
worth less to counsel than a cited fact plus an honest "unknown". Tests enforce
both halves: exposure may cite only rule_ids that exist in the ruleset, and no
numeric score field may be introduced.

## 4. Administration

### 4.1 RBAC (three roles)
`core/access.py` is the single source of truth. **platform_admin** (bootstrap
via ADMIN_EMAILS): everything. **agency_admin**: their agency's cities —
attest, edit, manage users. **viewer**: read-only on granted cities.
Enforcement is real on all reads; Sentinel DLP reads are **agency-scoped** —
the platform admin sees all telemetry, an agency admin/viewer sees only their
own cities' events/devices, and untagged rows are platform-admin-only
(fail-secure for employee-monitoring data).

### 4.2 Target registry management
Add/deactivate targets; **edit scan settings post-creation** (PATCH): the
WAF/Cloudflare flag (excludes a city from bulk scans and protects Deep Scan
results from being overwritten), tags, URL. Gear icon on city pages; inline
shield toggle on the Targets page.
- API: `GET/POST/PATCH/DELETE /api/targets[...]`, `POST /api/targets/bulk`.

### 4.3 Users, agencies, audit log
Admin console for user/agency management (agencies own cities; grants bound
viewers). Every consequential action (audits, imports, attestations, document
generation, setting changes) writes to an audit log.
- API: `/api/auth/users`, `/api/agencies`, `GET /api/logs`.

## 5. Sentinel — internal browser DLP

### 5.1 Sentinel extension + telemetry
Browser extension (separate `webextension/` codebase) guarding AI ingestion
against PII/HIPAA/CJIS leaks. Local-first detection; **metadata-only**
reporting (server rejects, not strips, any packet carrying prompt text).
Trigger-based scanning (submit/drop events), not keystroke logging.
- Ingest: `POST /api/sentinel/ingest` (X-Sentinel-Token device auth;
  unconfigured ingest rejects everything — fail-secure).
- Dashboards: events by policy/site, device heartbeat health (silent device =
  possible bypass), `GET /api/sentinel/events|devices|summary`.

## 6. Platform experience

### 6.1 Responsive UI (desktop, tablet, phone)
The console is usable on a phone, not only a laptop. The navigation drawer is
permanent at ≥ 960px and becomes a dismissible overlay below it, with a compact app
bar + hamburger appearing only on small screens. Every data table stacks into
labelled cards below 600px — set once as a global Vuetify default, so tables added
later inherit it. Container padding, toolbars and long URLs adapt; wide content
scrolls inside its own wrapper rather than forcing the page sideways. The mobile
breakpoint is **pinned explicitly** (`md` / 960px) rather than inherited from the
framework default (1280px), so the desktop layout is unchanged.

### 6.2 Themes
Light and **Stealth** (dark, low-glare) palettes, toggled from the nav drawer and
persisted per user.
