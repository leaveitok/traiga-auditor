# AI Use-Case Inventory — Specification v1.1 (updated 2026-07-18)

## Purpose

The system-of-record for every AI system an agency runs — **discovered
automatically** by the scan pipeline (and later Sentinel), **confirmed** by a
human. The registry a city shows an auditor, its council, or the AG's office
when asked "what AI do you have and who owns it?"

Design principle (agreed with Chris): **the user never starts from blank.**
Rows appear from discovery; the human's job is to confirm, assign an owner,
and fill in context — not to author records from memory.

## Data model — `ai_assets` (governance Firestore DB, all values strings)

| Field | Notes |
|---|---|
| `asset_key` | doc id. Discovered: `{city}::{vendor_id}` (slugified). Declared: `{city}::decl-{uuid8}` |
| `city` | tenancy key — RBAC scoping reuses `filter_rows` unchanged |
| `vendor_id` / `display_name` | from fingerprint schema, or free text when declared |
| `asset_types_json` | JSON list (chatbot, automated_intake_widget, …) |
| `provenance` | primary/first source: `discovered_scan` \| `discovered_agenda` \| `discovered_procurement` \| `discovered_sentinel` \| `declared` (future: `discovered_budget`, `discovered_oauth`, `discovered_network`, `discovered_vendor_feature`) |
| `tool_id` | canonical cross-channel id (identity resolver). Registry key is `{city}::{tool_id}` so the same tool found by multiple channels is ONE row |
| `discovery_sources_json` | machine field: append-unioned list of every channel that found this tool `[{provenance, observed_utc, evidence}]` — the "found by scan + Sentinel + procurement" evidence |
| `lifecycle_status` | `discovered` → `attested` → `retired` |
| `presence` | `active` \| `not_reobserved` (city crawled OK but asset absent) |
| `first_observed_utc` / `last_observed_utc` | scan timestamps (declared: creation time) |
| `page_url`, `match_confidence`, `evidence_json` | discovery evidence (matched indicators) |
| `owner_email`, `owner_name` | assigned accountable owner |
| `attested_by`, `attested_utc`, `attestation_note` | who confirmed the record |
| `department`, `purpose`, `data_categories_json` | human context (PII / CJIS / HIPAA / none) |
| `next_review_utc` | attested + 365 days (re-attestation cadence) |

**Merge rule (critical):** scan upserts refresh only the *machine* fields
(last_observed, confidence, evidence, presence). Human fields (owner,
attestation, department, purpose, data categories, lifecycle) are **never
overwritten by a scan**. A scan can move `presence`, not `lifecycle_status`.

**Derived at read time (never stored, so never stale):**
- `disclosure_status` — join against open violations for (city, vendor_id):
  any open ⇒ `non_compliant`, else if scanned ⇒ `compliant`, else `not_assessed`.
- `deployment_state` — derived from `provenance`, NOT stored: `discovered_scan`
  ⇒ **Live on site** (observed running now — a real disclosure obligation);
  `discovered_agenda` / `discovered_procurement` / `discovered_budget` ⇒
  **Procured / Budgeted · verify** (found in a record, not confirmed deployed);
  `discovered_sentinel` ⇒ **Staff-reported**; `declared` ⇒ **Self-declared**.
  This is what stops an implementation-timing gap (bought but not yet live) from
  reading as live non-compliance. Note the compliance math already agrees:
  `disclosure_status` is only computed for `discovered_scan`; every other
  provenance is `not_assessed` and never produces a violation or a cure clock.
- `statutory_exposure` — from `Governance_Profile.statutory_exposure`, the TRAIGA
  rules an asset's FUNCTION implicates (deterministic; needs no vendor internals).
- `obligations` — applicable rules from `Compliance_Ruleset.External_Transparency_Module`
  (rule_id, title, citation, severity). Framework crosswalk grows by adding
  rule modules to the schema — no inventory code change (governance-as-code).

## Discovery hook (pipeline)

After per-city persist in `run_full_audit`: upsert each deduped detected asset;
then, for that city's previously `discovered_scan` assets NOT re-observed in a
successful crawl, set `presence=not_reobserved`. Wrapped in try/except — the
inventory write must never break a scan. No writes when the crawl failed
(fail-secure: absence of evidence ≠ evidence of absence).

## API — `/api/inventory`

- `GET ""` — list, principal-scoped (`filter_rows`), enriched (disclosure_status,
  obligations, parsed JSON fields). Optional `?city=`.
- `POST ""` — declare an asset. platform_admin or agency_admin, within city
  scope (403 otherwise — fail-secure). Declared records are born attested by
  their declarer.
- `PATCH "/{asset_key}"` — attest / assign owner / edit context / retire.
  Same role rule. Whitelisted fields only; machine fields not patchable.
  Every attest/retire appends to the audit log (actor-attributed).

## UI

- **Inventory view** (nav: "AI Inventory", all roles read): table = one row per
  asset. Columns: asset (name + type), city, provenance chip (naming the actual
  channel — Website scan / Council agenda / Procurement / Budget / Staff usage /
  Declared) plus a deployment badge (*Live on site* vs *Procured · verify*),
  disclosure chip,
  presence badge, owner, lifecycle chip, last observed. Expand row → evidence
  (page URL, matched signals, confidence) + obligations with citations.
  Actions (admin roles): **Confirm & Attest** (dialog pre-filled from
  discovery; adds owner, department, purpose, data categories), **Declare AI
  system** (for what scans can't see: internal tools, vendor systems), Retire.
- **Agency scoping**: RBAC does the work — an agency admin's view IS their
  agency profile's inventory. Platform admin sees all cities + city filter.
- **CityDetailView**: embedded panel of that city's assets (same component,
  `city` prop).
- KPI strip: total / needs attestation / attested / undisclosed (open
  violations) — the "needs attestation" count is the workflow driver.

## RBAC

Read: any authenticated principal, rows filtered to visible cities.
Write (declare/attest/patch): `platform_admin`, or `agency_admin` whose city
set contains the asset's city. Viewers: read-only. Unknown role: nothing.

## Out of scope v1 (explicitly)

Bulk import/export (CSV export), per-asset documents/contracts.

**Shipped since v1.0:** Sentinel-fed usage assets, agenda + procurement channels,
the NIST AI RMF / ISO 42001 crosswalk (Safe Harbor module, 3 frameworks), and the
vendor `Governance_Profile`. Still design-only: budget channel, bundled
vendor-AI-feature detection, and automated vendor enrichment — see
`docs/DOC_STATUS.md` for what is live vs proposed.
