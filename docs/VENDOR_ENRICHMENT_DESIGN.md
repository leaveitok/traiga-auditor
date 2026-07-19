# Vendor Governance Enrichment — Design / Scope (DRAFT for review)

> ⚠ **STATUS: DESIGN ONLY — NOT IN PRODUCTION.** Nothing described in this document is built or deployed. It is a proposal for review.

Status: proposed, not built. Author: architecture pass, 2026-07-13.
Grounded in the live PoC: `docs/CITIBOT_ENRICHMENT_POC.md`.
Sibling of the other channel design docs.

## 1. Goal / non-goals

**Goal:** cut the manual attestation burden on a vendor's `Governance_Profile` by
auto-populating the *documented* facts **with citations**, so a human **confirms** rather
than **researches**, and only genuinely-undisclosed items remain to attest.

**Non-goals (hard limits proven by the PoC):**
- NOT an auto-attestor and NOT a risk score. Every auto-filled value is an
  `unverified_candidate` until a person confirms it.
- Does NOT replace the vendor security questionnaire — the facts that matter most
  (SOC 2, FedRAMP/StateRAMP, resident-data handling) were not publicly answerable for
  Citibot and will often stay manual.
- Never launder a vendor marketing **claim** into a **fact**; never assert a document
  applies to the municipal deployment when it is scoped to the vendor's marketing site.

## 2. What the PoC proved (design constraints)

- Reliably auto-fillable: policy/ethics/trust URLs, notable clauses (Citibot: indefinite
  retention, no-deletion, third-party ad sharing), governance affiliations (GovAI Coalition).
- Authoritative when present: certification **registries** — the highest-value auto-confirms.
- Frequently NOT public → stays unknown: SOC 2 / FedRAMP / StateRAMP, data residency, model
  training, DPA/sub-processors.
- **Scope trap:** a public privacy policy may govern the wrong data subject (site visitors,
  not residents). Scope must be a first-class flag, not silently ignored.

## 3. Design — a three-stage evidence-gatherer (not an oracle)

**Stage A — Registry check (authoritative, structured, do first).**
Query the authoritative certification registries by vendor name:
FedRAMP Marketplace, StateRAMP Authorized Product List, CSA STAR. A hit here is the
strongest auto-confirmable fact (third-party attested). Absence = "no public listing",
NOT "uncertified".

**Stage B — Public-source harvest + extraction (candidate, cited).**
Fetch a **curated allowlist** — the vendor's own domain (privacy, security/trust, DPA,
ethics pages) — then LLM-extract each documented fact as:
`{ value, quoted_snippet, source_url, as_of, state, scope }` where
`state ∈ {documented, vendor_stated, not_published, unknown}` and
`scope ∈ {marketing_site, product_deployment, unclear}`. Surface **notable clauses**
(retention, deletion, data sharing, training) explicitly for reviewer attention.

**Stage C — Gap questionnaire (turn the unknowns into one form).**
For every field still `unknown`, auto-generate a **targeted vendor questionnaire**
pre-filled with what Stages A–B found, so the human sends a short form, not a research
project. This is the real labor-saver for the facts that never go public.

## 4. Guardrails (the no-fabrication contract)

- No write without a `source_url` (Stage B) or a registry record id (Stage A).
- Everything `unverified_candidate` until human-confirmed; confirmation is one click.
- Registry (third-party) evidence ranks above vendor self-assertion; both above absence.
- `scope` flag mandatory on every extracted clause; `unclear`/`marketing_site` items are
  shown as "verify applies to your deployment", never asserted against the vendor.
- No composite score — consistent with `Governance_Profile`.

## 5. Architecture placement (existing principles)

- **I/O + LLM:** `core/governance/vendor_enrichment.py` — allowlist fetchers + registry
  clients + LLM extractor; all fetchers injectable for offline tests.
- **Writes to:** `AI_Tool_Catalog[tool].governance_profile` (the Tier-2 fields already
  defined), each value carrying source/as_of/state/scope + `unverified_candidate`.
- **Route:** `POST /api/governance/enrich/{vendor_id}` (platform admin), on-demand; a batch
  refresh job later.
- **Frontend:** a "Vendor governance" panel — cited facts with **Confirm** buttons, notable
  clauses highlighted, and an **export/send gap questionnaire** action.
- Storage-agnostic engine; two-layer service; auth placeholders — unchanged.
- **Evidence handling:** store the **source_url + short quoted snippet + as_of + content
  hash**, NOT the full third-party document (copyright/ToS); the snippet is the citation.

## 6. Cost

Per vendor: a few HTTP fetches + up to 3 registry lookups + one Flash-Lite extraction
(~few k tokens). Pennies per vendor at $0.10/$0.40 per 1M; cached with a periodic refresh.
Runs per vendor in the catalog, not per city — so it amortizes across all cities on that
vendor (network effect).

## 7. Testing (offline, no live HTTP/LLM)

- Registry parse: fixture JSON → cert facts (present / absent cases).
- Extraction: fixture page text (the real Citibot pages make good fixtures) → cited facts
  with correct `state`/`scope`; assert nothing written without a source_url.
- Scope flag: a marketing-site policy → `scope=marketing_site`, surfaced as "verify".
- Gap questionnaire: unknown fields → a questionnaire pre-filled with found facts.

## 8. Phasing

- **Phase A** (~1 day): registry checks + policy/trust URL harvest + write cited candidates.
  Highest ROI, lowest risk, no interpretation.
- **Phase B** (~1–2 days): LLM clause extraction with `state`/`scope` + notable-clause
  surfacing + the Confirm UI.
- **Phase C** (~1 day): auto-generated, pre-filled vendor gap questionnaire (export/send).

## 9. Open decisions (need your call)

1. **Source allowlist for v1** — which registries (FedRAMP + StateRAMP + CSA STAR enough?)
   and do we include GovAI-Coalition-style membership lists?
2. **Refresh cadence** — on-demand only, or a periodic (quarterly?) re-enrich per vendor?
3. **Who confirms candidates** — platform admin only, or may an agency admin confirm for
   their own city's vendors?
4. **Gap questionnaire delivery** — export a PDF/form for the city to send, or (later) email
   it to the vendor contact directly?
