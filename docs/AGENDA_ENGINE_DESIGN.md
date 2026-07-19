# Council-Agenda Discovery Engine — Design Spec (RFC)

Status: **Draft for review** · Date: 2026-07-09
Audience: engineering (build), CIO-founder (approve flagged decisions).

A new discovery channel (`discovered_agenda`) that scrapes municipal council
agendas / minutes for **awarded tech contracts**, extracts the vendor + product,
matches against the AI tool catalog, and merges results into the AI registry.
It reuses the crawl infrastructure and the procurement matcher already built; it
is a **separate engine** from the website compliance scanner, with **isolated
execution**. Nothing here is built yet.

---

## 1. Why this channel is worth building

- **Public data, zero onboarding.** Council agendas are legally required to be
  posted (Texas Open Meetings Act). Unlike OAuth (needs admin consent) or the
  procurement CSV (needs an upload), this needs *nothing from the city* — so it
  runs on **prospects**, extending the "scan them before the meeting" sales
  motion to procurement.
- **Earliest lifecycle signal.** It catches AI at the contract **award** — before
  the tool is deployed (website scanner) or used (Sentinel).
- **Reuses the matcher.** An agenda item ("award a contract to [Vendor] for
  [Product]") becomes a `{vendor, product, amount, city}` row → the exact
  procurement normalizer + catalog + AI-keyword screen already shipped.
- **A dataset no competitor has.** Award items across 1,200 cities = unique
  cross-jurisdiction AI-procurement intelligence; feeds vendor-risk.

---

## 2. Architecture decision: shared substrate, separate engines, isolated execution

This is the core question. The two systems do different jobs; share only the
expensive, general infrastructure.

| Concern | Website compliance scanner | Council-agenda engine | Decision |
|---|---|---|---|
| **Fetch / crawl** (Playwright, stealth, WAF, residential proxy, Deep Scan) | needs it | needs it | **SHARE** — one fetch layer; never duplicate the proxy/Deep-Scan |
| **Target surface** | the city `.gov` website | the agenda portal (Legistar/Granicus/CivicPlus… often a different domain) | **SEPARATE** target config (`agenda_url`) |
| **Processing** | DOM fingerprinting (regex indicators) | text/PDF segmentation + LLM entity extraction | **SEPARATE** engine modules |
| **Goal / output** | disclosure **violations** + 60-day cure + scorecard | **discovery** assets only | **SEPARATE** — agenda engine runs NO disclosure validator / cure engine; an award is not a disclosure violation |
| **Identity + matcher + catalog** | — | reuses procurement matcher | **SHARE** |
| **Registry + merge** | writes ai_assets + scorecard/violations | writes ai_assets only (`discovered_agenda`) | **SHARE** the registry; agenda writes discovery rows only |
| **Cadence / cost** | nightly, proxy-cost-controlled | weekly-ish + LLM API cost | **SEPARATE** schedule + budget |
| **Execution** | the core nightly product | heavy LLM/PDF workload | **ISOLATE** — own worker/service at scale so it can't starve the compliance scan |

**Why isolate execution (your instinct, sharpened):** at 1,200 cities the agenda
engine's LLM + PDF-parsing load, run inline with the nightly scan, would contend
for CPU/memory and stall the core product — the same failure class durable audit
state just fixed (heavy work on a shared instance starves everything else). So:

- **Beta:** in-process, flag-gated (`AGENDA_ENGINE_ENABLED`), a handful of cities.
- **Scale:** dedicated Cloud Run service / queue worker, own service account,
  own run state (never shares the compliance-scan audit slot) — mirrors the
  planned Sentinel service split (ROADMAP H3-3).

Net: **do not duplicate the crawler or the matcher; do separate the engine, its
output semantics, its schedule/budget, and its execution.**

### 2.1 Residential-proxy cost batching (demand-driven, not WAF-flag-coupled)

The residential proxy is the main marginal cost, so minimize proxy pulls — but
do NOT couple agenda-proxy use to the website's `cloudflare_protected` flag: the
agenda portal is almost always a **different third-party host** (Legistar,
Granicus, CivicPlus) that usually is NOT behind the city's WAF. Coupling would
waste credits on open portals and miss blocked ones. Instead:

- **Demand-driven:** the agenda engine escalates to the proxy on its OWN WAF
  detection (`engine/crawler.is_waf_challenge`), so it pays only when the
  *portal* actually blocks datacenter IPs.
- **Opportunistic batching (Chris's cost idea, refined):** when a compliance
  scan for a city is already in a proxied session and that city's agenda scan is
  due, run the agenda fetch in the **same** proxied session to amortize per-
  session overhead. Coordinated via a shared "city is proxied now" signal, not a
  static flag.
- **Config:** `AGENDA_PROXY_URL` / `AGENDA_PROXY_ONLY_FLAGGED` (siblings of the
  scanner's proxy config); secrets in Secret Manager, never in code.

---

## 3. Pipeline

```
targets(agenda_url) 
  → [1] identify agenda PLATFORM (fingerprint: Legistar/Granicus, CivicPlus, CivicClerk, PrimeGov, Diligent)
  → [2] FETCH meeting list + agenda items / PDF packets   (SHARED crawler: proxy, WAF, Deep Scan)
  → [3] SEGMENT the agenda into individual items
  → [4] PRE-FILTER to procurement/award items             (keyword gate — bounds LLM spend)
  → [5] LLM EXTRACT {vendor, product, action, amount, dept, meeting_date}  (strict JSON schema)
  → [6] MATCH each item                                   (SHARED: procurement.normalize + AI-keyword screen)
  → [7] MERGE as provenance=discovered_agenda             (SHARED: merge_discovered_assets)
  → registry → (human review for candidates)
```

Fail-secure throughout: an item we cannot confidently parse becomes a **candidate**
for human review (never a silent determination); a blocked/failed fetch is
recorded, not treated as "no AI procured."

---

## 4. Agenda-platform fingerprinting (the tractable entry point)

Municipal agendas run on a handful of platforms — fingerprint the platform (URL
patterns + DOM markers) exactly like website vendors, then pick the parser:

| Platform | Signals | Notes |
|---|---|---|
| **Granicus / Legistar** | `*.legistar.com`, `granicus.com`, "InSite"/"Legistar" markers | Most common in larger TX cities; often structured (item tables + PDF packets). **Start here.** |
| **CivicPlus (Agenda/Municode Meetings)** | `civicplus.com`, `*.civicweb.net` | Very common in mid/small cities. |
| **CivicClerk** (CivicPlus/Municode) | `*.civicclerk.com` | Growing. |
| **PrimeGov** | `*.primegov.com` | |
| **Diligent Community (iCompass)** | `*.iqm2.com`, `*.diligent.com` | |
| **NovusAGENDA** | `novusagenda.com` | |

Start with the **2–3 dominant platforms among the TX/TAGITM cohort** (likely
Legistar/Granicus + CivicPlus + CivicClerk). Each platform = one parser that
lists meetings and yields per-item text + packet-PDF links.

---

## 5. Extraction (the hard part)

Agenda items are semi-structured prose. Strategy:

1. **Segment** the agenda into items (platform parser or heading heuristics).
2. **Pre-filter** to procurement/award items with a cheap keyword gate
   ("award", "contract", "purchase", "agreement", "professional services",
   "sole source", "RFP", "renew") — this bounds LLM token spend.
3. **LLM extract** structured fields with a **strict JSON schema** + low
   temperature: `{vendor, product_or_service, action ∈ {awarded, renewed,
   discussed, terminated}, amount_band, department, meeting_date}`. Keep the
   source item text as evidence.
4. **Match** via the shared `procurement.normalize` (vendor + product + AI-keyword
   screen). Catalog hit → `procured_ai`; keyword-only → `procured_ai_candidate`.
5. **Human review** confirms candidates (consistent with the platform's
   candidate-signal / counsel-review posture).

Cost control: LLM runs only on pre-filtered items; batch per meeting; cache by
item hash so re-scrapes don't re-spend.

---

## 6. Data model (additive)

- **targets:** add `agenda_url` (+ optional `agenda_platform` hint). One city row
  carries both its website and its agenda portal.
- **provenance:** `discovered_agenda`; `asset_types` `["procured_ai"]` or
  `["procured_ai_candidate"]`.
- **evidence:** `{meeting_date, meeting_title, item_title, action, amount_band,
  source_url}` — enough to defend the finding, no more.
- **No writes to scorecard/violations** from this engine. Discovery only. (If a
  city later *deploys* that AI publicly, the website scanner independently opens
  any disclosure violation — the two remain decoupled and merge on the canonical
  `tool_id`.)

---

## 7. Reuse map (explicit — what is SHARED)

| Need | Reused component |
|---|---|
| Fetch pages/PDFs, WAF/proxy/Deep Scan | `engine/crawler.py` (`crawl_site`, chrome-capture) |
| Canonical identity + catalog | `engine/collectors/identity.py`, `SCHEMA_DEFINITION.json` `AI_Tool_Catalog` |
| Vendor/product/AI-keyword matching | `engine/collectors/procurement.py` |
| Merge into registry (multi-source union) | `core/discovery/merge.py` |
| Collector pattern | new `engine/collectors/agenda.py` (pure: parsed items → assets) + `core/discovery/agenda_source.py` (orchestrator: fetch + LLM + merge) |

New modules only: the platform parsers, the LLM extractor, and the orchestrator.
Everything downstream of "a `{vendor, product}` row" already exists.

---

## 8. Compliance, legal & security

- **Public-record data** (Open Meetings Act) — low privacy risk, but agendas can
  name individuals (staff, applicants). Store only vendor/product/amount/meeting
  metadata as evidence; do not persist incidental PII.
- **Candidate signals, not determinations** — every extraction needs human
  confirmation; generated documents keep the counsel-review disclaimer.
- **Out-of-line observer** — read-only fetch of public records; never submits or
  disrupts.
- **LLM handling** — send only pre-filtered item text; use a provider/config with
  **enterprise no-training terms** (you're selling AI governance — the extraction
  step must itself be governable and documented); API key in Secret Manager;
  log the model + prompt version for auditability.

---

## 9. Effort / impact sequence

1. `agenda_url` on targets + agenda-platform fingerprint (2–3 platforms). *(Low–Med)*
2. Fetch + segment for the first platform (Legistar/Granicus — common + structured). *(Med)*
3. LLM extractor + wire to the procurement matcher + merge as `discovered_agenda` — in-process, flag-gated, one pilot city. *(Med–High)*
4. Human-review surface for candidate rows in the Inventory (reuse the existing attest flow). *(Low)*
5. Execution split (own worker + schedule) + more platforms + re-scrape caching. *(High — at pilot scale)*

---

## 10. Open decisions (need sign-off before build)

1. **First agenda platform** — pick by the pilot city's system (Legistar/Granicus is the safe default).
2. **LLM provider/model + data posture** — enterprise no-train terms required; which provider, and how much extraction do we log for our own audit trail?
3. **Execution split timing** — in-process flag-gated for beta vs. dedicated worker; when to split.
4. **Target model** — reuse `targets.agenda_url` (recommended) vs. a separate agenda target registry.
5. **Scope of pilot** — how many cities / how far back in meeting history to scrape initially.
```
