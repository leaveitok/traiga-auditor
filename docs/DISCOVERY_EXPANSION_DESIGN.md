# Discovery Expansion — Design Spec (RFC)

Status: **Draft for review** · Author: Chief-of-Staff design pass · Date: 2026-07-09
Audience: engineering (build), CIO-founder (approve the flagged decisions).

This is a **forward-looking design**, not an as-built doc. It describes how to
widen the platform's discovery surface — the moat — by adding new *channels*
into the existing AI registry, without touching anything downstream of the
registry (cure engine, scorecard, statutory artifacts). It is written to the
project's architecture principles (two-layer service abstraction, interface-first,
single swap point, storage-agnostic engine, governance-as-code, security
placeholders, testability). Nothing here is built yet.

---

## 1. Thesis and scope

Discovery is the differentiator competitors (Trustible et al.) structurally
cannot copy: their inventory is fed by human intake and vendor docs; ours is fed
by *finding* AI nobody declared. Today the discovery surface is three channels
feeding one registry:

- `discovered_scan` — external website scanner (`engine/pipeline.py::_feed_inventory`)
- `discovered_sentinel` — browser-fleet DLP (`core/sentinel_feed.py`)
- `declared` — human-entered (`api/routes/inventory.py`)

This RFC adds four new channels and the connective tissue that unifies them:

| # | Channel | New provenance | Source | Effort | Differentiation |
|---|---|---|---|---|---|
| A | **SaaS / OAuth-grant** | `discovered_oauth` | M365 / Google Workspace admin APIs | High | **Flagship** — finds authorized shadow-AI SaaS nothing else sees |
| B | **Procurement / contract match** | `discovered_procurement` | Uploaded vendor/spend CSV | Low–Med | Ties discovery to vendor-risk; no external API |
| C | **Network / DNS egress** | `discovered_network` | Uploaded egress/DNS logs | Med | Security-buyer signal; catches API-level AI use |
| D | **Scanner depth: generic-AI** | `discovered_scan` (unchanged) | Existing crawl captures | Med | Catches un-fingerprinted AI (chat widgets, LLM search) |
| E | **Cross-channel identity + vendor rollup** | — (substrate) | All channels | Med | One canonical asset per tool; multi-source evidence; free vendor inventory |

**Non-negotiable invariant:** every channel is *only* a new way to produce
`ai_assets` rows. It reuses `upsert_ai_asset` (merge contract), read-time
derivation (`disclosure_status`, `obligations`), the cure engine, and the
§552 artifact generators unchanged. If a channel needs a change downstream of
the registry, the design is wrong.

> Note: "vendor-from-fingerprint" from the strategy discussion is **already
> shipped** — `_feed_inventory` creates an asset per detected vendor. Its
> remaining value (a cross-city *vendor* rollup) is delivered by channel **E**,
> not a separate collector.

---

## 2. The unifying abstraction (interface-first)

Two collectors exist today, written ad hoc (`_feed_inventory`, `sentinel_feed`).
Before adding four more, define the contract once so all six are consistent,
testable, and cheap to maintain.

### 2.1 The `DiscoveryCollector` split (respects "engine is storage-agnostic")

The project rule is that `engine/` is permanently storage-agnostic (pure
data-in/data-out) and never imports repositories. We honor it by splitting every
channel into two layers:

```
engine/collectors/<channel>.py     # PURE normalizer: raw source data -> [DiscoveredAsset dict]
                                    #   no I/O, no repo, no network. Fully unit-testable.
core/discovery/<channel>_source.py  # ORCHESTRATOR: does the I/O (API call / file read /
                                    #   log parse), calls the pure normalizer, merges via repo.
```

This mirrors what already exists: `sentinel_feed.build_usage_assets()` is a pure
normalizer and `sentinel_feed.sync_to_inventory()` is its orchestrator. We are
generalizing that proven shape, not inventing one.

### 2.2 Backend interface (Protocol) — define before any implementation

```python
# core/discovery/collector.py
from typing import Any, Dict, List, Protocol, TypedDict

class DiscoveredAsset(TypedDict, total=False):
    """One normalized discovery finding. All values become strings on write
    (Sheets/Firestore contract). MACHINE fields only — never human fields."""
    tool_id:        str   # canonical id (see §3 identity resolver)
    city:           str
    vendor_id:      str
    display_name:   str
    asset_types:    List[str]
    provenance:     str   # discovered_oauth | discovered_procurement | ...
    presence:       str   # active | observed | not_reobserved
    evidence:       Dict[str, Any]   # channel-specific proof (grant id, contract line, host)
    confidence:     float
    observed_utc:   str

class DiscoveryResult(TypedDict):
    assets:  List[DiscoveredAsset]
    skipped: int                    # findings we could not attribute (fail-secure)
    source_meta: Dict[str, Any]     # counts, tenant id, file name — for the audit log

class DiscoveryCollector(Protocol):
    """Contract every channel satisfies. Storage-agnostic: collect() returns
    dicts; the orchestrator merges them. Injectable for tests (pass a fake
    source client + MockGovernanceRepository)."""
    provenance: str
    def collect(self, context: Dict[str, Any]) -> DiscoveryResult:
        # TODO: enforce system-level invocation only (auth placeholder)
        # TODO: scope results to the requesting principal's cities
        ...
```

### 2.3 Shared merge helper (one place, reused by all channels)

```python
# core/discovery/merge.py
def merge_discovered_assets(repo, result: DiscoveryResult) -> Dict[str, Any]:
    """Upsert every DiscoveredAsset via the repo's merge-preserving
    upsert_ai_asset. Accumulates multi-source evidence (see §3.2). Human fields
    are never touched. Returns {written, cities, skipped, errors}. Wrapped so a
    single bad row never aborts the batch (mirrors _feed_inventory / sentinel_feed).
    # TODO: enforce system-level write only (auth placeholder)"""
```

**Single swap point (project principle #3):** a channel is registered in exactly
one place — a `COLLECTORS` registry in `core/discovery/__init__.py`. Adding a
channel touches: one pure normalizer, one orchestrator, one registry line, one
schema alias block, one route entry. It never touches the cure engine, scorecard,
or artifact code.

---

## 3. Cross-channel identity — the one decision that shapes everything (DECIDED: canonical `tool_id`, 2026-07-09)

Today the same tool found by two channels becomes **two rows**: the scanner keys
`{city}::{vendor_id}`, Sentinel keys `sentinel:{site}@{city}`. As channels
multiply, ChatGPT could appear as 4 rows for one city. That is a worse registry,
not a better one.

### 3.1 Proposal: a canonical `tool_id` resolver

Add an alias table to the vendor library in `SCHEMA_DEFINITION.json`
(governance-as-code — data, not code):

```jsonc
// SCHEMA_DEFINITION.json → vendors[]
{
  "vendor_id": "openai_chatgpt",
  "display_name": "ChatGPT (OpenAI)",
  "aliases": {
    "sentinel_site_ids": ["chatgpt", "openai"],
    "oauth_app_ids":     ["<M365 app guid>", "<google client id>"],
    "domains":           ["chatgpt.com", "openai.com", "api.openai.com"],
    "procurement_names": ["openai", "chatgpt enterprise"]
  }
}
```

A pure resolver `engine/collectors/identity.py::resolve_tool_id(channel, raw_id)
-> vendor_id | "unknown:<raw>"` maps any channel's raw identifier to one
canonical `vendor_id`. Every channel keys its asset `{city}::{vendor_id}`. Result:
**one canonical asset per (city, tool)**, regardless of how many channels found it.

### 3.2 Multi-source evidence (small merge-contract extension)

`provenance` stays as the *primary* (first) source for backward compatibility.
Add a machine field `discovery_sources_json` — an append-merged list of
`{provenance, observed_utc, evidence}` so the registry shows *"ChatGPT — found
by scan + Sentinel + OAuth."* Because `upsert_ai_asset` overwrites fields, the
merge helper (§2.3) must **read existing sources, union, then write** (exactly
how `_feed_inventory` already reads existing rows before writing). No change to
the repository Protocol is required.

**Why this is worth a decision:** it slightly changes the keying of the existing
Sentinel channel (`sentinel:site@city` → `{city}::openai_chatgpt`) and adds one
field. Upside: a coherent registry and the "3 channels agree" evidence story that
sells. **Recommendation: adopt it now**, before four channels harden the old
split. Migration is a one-time re-key of existing `discovered_sentinel` rows.

Alternative (lower effort, worse registry): keep per-channel rows, add a UI
"group by tool" view. Rejected unless you want to defer the migration.

---

## 4. Per-channel design

Each channel: **source → auth/deps → normalizer → matching → asset shape →
security/compliance → effort → risks.** All normalizers are pure and unit-tested;
all orchestrators are integration-tested with a fake source client + MockRepo.

### A. SaaS / OAuth-grant discovery (flagship) — `discovered_oauth`

- **Source:** the city's identity tenant. Microsoft Entra ID (Graph
  `/servicePrincipals`, `/oauth2PermissionGrants`, app role assignments) and
  Google Workspace (Admin SDK `tokens`/`token.list`, Marketplace apps). These
  list every third-party app a user or admin granted access to.
- **Auth/deps (SECURITY-SENSITIVE — see §7):** read-only, least-privilege scopes
  (`Application.Read.All` / `Directory.Read.All` on Entra;
  `admin.directory.token.readonly` on Google). Tenant admin consent required.
  Credentials (client id/secret or workload-identity federation) live in Secret
  Manager, **never in code or the repo** — same pattern as `SCAN_PROXY_URL`.
  Per-city tenant config stored as a target/agency attribute, not hard-coded.
- **Normalizer** (`engine/collectors/oauth.py`, pure): raw grant list +
  vendor alias index → `DiscoveredAsset[]`. Match each app's `appId`/`clientId`
  against `aliases.oauth_app_ids`; fall back to publisher domain against
  `aliases.domains`; unmatched but AI-categorized apps become
  `vendor_id="unknown:<publisher>"` (surfaced for human triage, never dropped).
  Evidence = `{app_id, display_name, grant_scopes, granted_by, grant_utc}`.
- **Asset shape:** `provenance=discovered_oauth`, `presence=active`,
  `display_name` from the app, `asset_types=["saas_ai_tool"]`.
- **Compliance framing:** candidate signal; scopes are evidence of *access*, not
  proof of PHI/PII flow — the record says so, human confirms.
- **Effort:** High (two API integrations + admin-consent onboarding). Highest
  differentiation. Build the **normalizer + Google OR Microsoft first** (one
  tenant type), prove the demo, then add the second.
- **Risks:** admin-consent friction in onboarding; token/grant lists are large
  (paginate); false "AI" classification — gate on the alias table + an
  `ai_app_categories` allow-list in the schema.

### B. Procurement / contract match — `discovered_procurement`

- **Source:** a CSV/XLSX the city already has (vendor master, AP spend, contract
  register). Uploaded via UI — **no external API, no new credentials.** Reuses
  the existing bulk-import file-handling pattern (`POST /targets/bulk`).
- **Normalizer** (`engine/collectors/procurement.py`, pure): rows + alias index →
  assets. Fuzzy-match vendor name against `aliases.procurement_names` +
  `display_name` (normalized, token-set ratio). Evidence =
  `{contract_id, vendor_name_raw, amount, term}` (amounts are optional; store a
  band, not exact spend, to avoid over-collecting financial data).
- **Asset shape:** `provenance=discovered_procurement`, `presence` unset
  (contract ≠ live usage — it's a *procured* signal), `asset_types=["procured_ai"]`.
- **Compliance:** a contracted AI vendor is a strong "should be in the inventory"
  signal and directly feeds vendor-risk (module #3). Candidate only.
- **Effort:** Low–Medium. Great **second build** — self-contained, no auth
  surface, immediately useful, and it seeds the vendor library.
- **Risks:** name-matching false positives (require a confidence floor +
  human confirm); messy CSVs (reuse bulk-import's preview/validate/dedupe UX).

### C. Network / DNS egress — `discovered_network`

- **Source:** uploaded egress/proxy/DNS logs (Zscaler, Palo Alto, firewall, DNS
  resolver). Upload + parse; optionally a scheduled pull later.
- **Normalizer** (`engine/collectors/network.py`, pure): destination hosts →
  assets by matching against `aliases.domains`. Aggregate to
  `{tool_id, request_count, distinct_src_count, first/last_seen}` — **counts and
  hostnames only, never payloads or full URLs** (metadata-only, same rule as
  Sentinel). Evidence = `{matched_host, request_count, window}`.
- **Asset shape:** `provenance=discovered_network`, `presence=active`,
  `asset_types=["network_observed_ai"]`.
- **Compliance/privacy:** log data is employee-adjacent — apply the Sentinel wall
  (agency-scoped reads; strip source user identity to device/count granularity;
  drop query strings). Fail-secure: unmatched hosts are not guessed into tools.
- **Effort:** Medium (log-format variance). Build after A/B; highest value for a
  security/CISO buyer.
- **Risks:** log format sprawl (ship 2–3 parsers + a generic host-column mode);
  volume (cap + sample); privacy review before shipping.

### D. Scanner depth: generic-AI detection — `discovered_scan` (extends existing)

- **Source:** the crawl captures the scanner already collects — **no new
  ingestion.** Extends `engine/fingerprint_engine.py` and the schema.
- **How:** add a `generic_ai_signals` block to `SCHEMA_DEFINITION.json`
  (governance-as-code): behavioral indicators for un-fingerprinted AI — chat-widget
  DOM patterns, "ask a question / powered by AI" text markers, LLM-search
  endpoints, common embed hosts. A generic hit creates
  `vendor_id="unknown:generic_chat"` with lower confidence, flagged
  `needs_human_review` — surfaced, never auto-violated at full severity.
- **Compliance:** the highest-risk surface — AI in **consequential decisions**
  (eligibility, permitting, benefits) — gets a dedicated signal set and a
  higher-severity obligation mapping.
- **Effort:** Medium; pure schema + fingerprint-engine change with regression
  tests (reuse the `scan-triage` pattern: pull live DOM, run the engine offline,
  add signature + test).
- **Risks:** false positives from generic markers — keep generic hits
  low-confidence + human-review-gated; never let a generic hit alone open a
  cure-clock violation without confirmation.

---

## 5. Data-model changes (additive, governance-as-code)

- **Provenance enum:** add `discovered_oauth`, `discovered_procurement`,
  `discovered_network`. (Doc the enum in INVENTORY_SPEC; it's a string field, no
  migration.)
- **New machine fields on `ai_assets`:** `tool_id` (canonical),
  `discovery_sources_json` (append-merged list). Both machine — never overwrite
  human fields.
- **Schema (`SCHEMA_DEFINITION.json`) additions:** `aliases` block per vendor,
  `ai_app_categories` allow-list, `generic_ai_signals` block. All data; no engine
  change beyond the resolver + generic matcher.
- **No repository Protocol change.** `get_ai_assets` / `upsert_ai_asset` already
  suffice; multi-source union happens in the merge helper (read-modify-write).

---

## 6. Backend & frontend structure (two-layer abstraction)

**Backend**
```
engine/collectors/            # PURE normalizers (storage-agnostic, unit-tested)
  identity.py                 # resolve_tool_id(channel, raw_id) -> vendor_id
  oauth.py  procurement.py  network.py  generic_ai.py
core/discovery/
  collector.py                # DiscoveryCollector Protocol + typed dicts
  merge.py                    # merge_discovered_assets (multi-source union)
  __init__.py                 # COLLECTORS registry (single swap point)
  oauth_source.py  procurement_source.py  network_source.py   # orchestrators (I/O + repo)
api/routes/discovery.py       # thin handlers: call a collector via Depends(get_repository)
```
Route handlers stay thin and call the repo only — no logic (project rule). Each
route enforces RBAC (`resolve_principal` + city scoping) before invoking a
collector, and appends to `audit_log`.

**Frontend (components → stores → GovernanceService → API)**
- `services/types.js` — JSDoc typedefs for `DiscoveredAsset`, `DiscoveryResult`,
  `OAuthTenantConfig` **before** writing service methods (TS-ready).
- `services/GovernanceService.js` — one method per channel action
  (`runOAuthDiscovery(city)`, `uploadProcurementFile(...)`, etc.). Components
  never call Axios directly.
- `stores/discovery.js` (Pinia) — calls GovernanceService only.
- A **Discovery view** — one screen showing all channels, last-run status per
  channel, and the "found by N sources" registry rollup. Each finding links into
  the existing Inventory row (Confirm & Attest reused unchanged).

---

## 7. Security & compliance (per project standards)

- **Least-privilege, read-only** OAuth scopes; admin consent per tenant; tokens
  and secrets in Secret Manager only (never code/repo/logs). Workload-identity
  federation preferred over stored client secrets where available.
- **Out-of-line observer:** discovery never modifies or disrupts a target system
  — it reads grant lists / logs / files. (OAuth discovery reads directory
  metadata; it does not exercise the apps.)
- **Metadata-only** for network + OAuth: hostnames, app ids, counts, scopes —
  never payloads, prompt text, or full URLs. Enforce with the same strict schema
  + prohibited-field strip used by Sentinel ingest.
- **Candidate signals, not determinations:** every discovered asset is a
  *candidate* requiring human confirmation and (for violations) counsel review —
  the platform's standing rule. Generated documents keep their counsel-review
  disclaimer.
- **RBAC + tenancy:** results scoped to the principal's cities; employee-adjacent
  channels (network, OAuth) inherit the Sentinel agency-scoped wall.
- **Every collector carries the standard auth/authz placeholder block** even
  before enforcement is wired (project principle #5).

---

## 8. Testing strategy (testability by design)

- **Pure normalizers** (`engine/collectors/*`): table-driven unit tests against
  captured fixtures (a redacted Graph grant list, a sample CSV, a log snippet).
  No network, no credentials — a test needing live creds is not a unit test.
- **Orchestrators** (`core/discovery/*_source`): inject a **fake source client**
  + `MockGovernanceRepository`; assert the right assets merged and human fields
  untouched (reuse the merge-contract assertions that already cover
  `sentinel_feed`).
- **Identity resolver:** exhaustive alias-table tests (each channel's raw id →
  expected canonical, plus the `unknown:` fallback).
- **Merge helper:** multi-source union test — same tool from two channels →
  one row, two `discovery_sources`, human fields preserved.
- **Regression fixtures per channel**, committed, so a schema/alias change that
  breaks matching fails a test (the `scan-triage` discipline, generalized).
- Runs under the standalone shim runner (no PyPI) and the future CI gate (H1-6).

---

## 9. Effort / impact sequence

1. **Substrate first (E):** identity resolver + alias table + multi-source merge.
   Everything else keys off it; doing it later forces a migration. *(Med)*
2. **Procurement (B):** self-contained, no auth surface, seeds vendor-risk,
   proves the collector pattern end-to-end. *(Low–Med)*
3. **OAuth flagship (A):** one tenant type first (pick Google *or* M365 by where
   Lewisville/pilot city lives), ship the "14 tools you never inventoried" demo,
   then add the second. *(High — but this is the sales magic)*
4. **Scanner depth (D):** schema + fingerprint extension; compounds every scan. *(Med)*
5. **Network egress (C):** security-buyer channel; do when a pilot asks for it. *(Med)*

Rationale: substrate unblocks all; procurement de-risks the pattern cheaply;
OAuth is the differentiator worth the cost; D and C follow demand.

---

## 10. Open decisions (need Chris's sign-off before build)

1. **Cross-channel identity (§3):** ✅ DECIDED 2026-07-09 — adopt canonical
   `tool_id` + multi-source evidence now. Includes a one-time re-key of existing
   `discovered_sentinel` rows.
2. **OAuth tenant type first:** Google Workspace or Microsoft Entra? (Pick by the
   pilot city's identity provider.)
3. **OAuth credential model:** workload-identity federation vs. stored client
   secret per tenant (security + onboarding trade-off).
4. **Network channel privacy posture:** how much source identity to retain
   (device/count only vs. user) — a policy decision you own as CIO.
5. **Scope of v1:** which 2 channels ship first (recommend E-substrate + B, then A).
```
