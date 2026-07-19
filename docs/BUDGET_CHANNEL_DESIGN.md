# Budget-Document Discovery Channel — Design / Scope (DRAFT for review)

> ⚠ **STATUS: DESIGN ONLY — NOT IN PRODUCTION.** Nothing described in this document is built or deployed. It is a proposal for review.

Status: proposed, not built. Author: architecture pass, 2026-07-13.
Sibling of `AGENDA_ENGINE_DESIGN.md`, `AGENDA_DEEP_TEXT_DESIGN.md`,
`DISCOVERY_EXPANSION_DESIGN.md`.

## 1. Why

A city's **adopted budget** is the most authoritative, comprehensive record of its tech
spend — every funded AI purchase, named, in one document, usually with dollar amounts.
Signal density is higher than agendas. It is a natural next discovery channel feeding the
same `ai_assets` registry as `provenance=discovered_budget`.

## 2. What we can reuse (most of it)

- **PDF text path** — `agenda_fetch.pdf_bytes_to_text` + `parse_pdf_agenda` already turn a
  large PDF into gated items (page/char caps to bound cost).
- **Procurement normalizer + AI-keyword screen** — same matcher, same (now curated)
  `ai_keywords`; provenance overridden to `discovered_budget`.
- **Site metadata fingerprint** — `Site_Metadata_Signatures` (built for agenda platforms)
  extends to budget platforms with JSON only (add `cleargov.com` / `opengov.com` host
  signatures → store `budget_platform` / `budget_url` on the target, pre-fill dialog).
- **Deployment/lifecycle badge** — already shipped: a `discovered_budget` item renders as
  **"Budgeted · verify"** (planned/funded, not verified live), so it never reads as a live
  disclosure violation.

The new engine work is therefore small: a budget source/orchestrator that fetches the
document, extracts text, gates + AI-screens, and merges — mirroring the agenda channel.

## 3. The hard part — discovery + format heterogeneity (verified)

Unlike agendas (Legistar gave ONE standard API across cities), budgets have **no common
API**. Cities publish on **ClearGov, OpenGov, Socrata, a plain PDF, or a self-hosted page**,
and the document is frequently **JS-rendered** or **300+ pages**.

- Verified: `https://city-lewisville-tx-cleardoc.cleargov.com/…` (ClearGov ClearDoc) returns
  a **JavaScript shell** on fetch — no content in the HTML. So a ClearDoc URL cannot be
  scraped directly; we need its **PDF export**, an API, or a JS-render fetch.

Approach (same pattern as agendas, so it's familiar and low-risk):

1. **PDF-first.** Prefer the downloadable budget PDF (most cities, incl. ClearGov, offer
   one). Reuse the existing PDF path. This covers the majority with no new rendering.
2. **Platform fingerprint + backstop.** Auto-detect `cleargov.com`/`opengov.com` on the
   website scan → store `budget_url`/`budget_platform`; let the user paste the budget PDF/
   URL when detection misses (identical to the Legistar-slug backstop).
3. **JS-render fallback (optional, later).** For JS-only sources, reuse the render tier /
   headless fetch to obtain text. Do NOT build this first.

Do not try to support every platform on day one — PDF + ClearGov/OpenGov detection covers a
large share of Texas municipalities.

## 4. Cost — bounded by the same regex-first discipline

Budgets are big (200–400 pages). Feeding a whole budget to the LLM would be wasteful.
Instead: extract text (pdfminer, capped) → run the **free** award/AI-keyword regex over it →
LLM-extract vendor/product **only** on the hits. Cost scales with document fetches, not
tokens. At Gemini 2.5 Flash-Lite ($0.10/$0.40 per 1M) the LLM portion is pennies per city
even in the worst case; the real cost is PDF parse time (bounded by page caps).

## 5. Provenance & lifecycle (already handled)

- provenance `discovered_budget`; writes **inventory rows only** — never a disclosure
  violation or a cure clock (same rule as agenda/procurement).
- Dashboard already distinguishes it: source chip **"Budget"**, deployment chip
  **"Budgeted · verify"** — so an as-yet-undeployed budgeted tool is not a false positive.

## 6. Architecture placement (unchanged principles)

- **Fetch (I/O):** `core/discovery/budget_fetch.py` (or extend `agenda_fetch`) —
  `fetch_budget_pdf(url, fetch_bytes)` → text; injectable for tests.
- **Pure:** reuse `engine/collectors/agenda.segment_items` + `is_procurement_item`, or a
  thin `engine/collectors/budget.py` if budget line-item segmentation differs.
- **Orchestrator:** `core/discovery/budget_source.py` — flag-gated, tenancy-scoped, merges
  via the repo, provenance `discovered_budget`. Route `POST /api/discovery/budget`.
- **Schema:** add budget-platform signatures to `Site_Metadata_Signatures`; add
  `budget_url`/`budget_platform` to the target (mirrors `agenda_client`).
- Storage-agnostic engine; two-layer service abstraction; auth placeholders — all preserved.

## 7. Testing

- `parse` over a real budget-PDF text fixture → gated AI line items.
- `fetch_budget_pdf` with injected `fetch_bytes` (fake PDF) — no live HTTP.
- Orchestrator with `MockRepo` — asserts a budgeted AI line merges as `discovered_budget`
  and surfaces as a candidate (never a violation).

## 8. Phasing

- **Phase A** (~1 day): paste-a-budget-PDF-URL path + PDF parse + AI screen + merge as
  `discovered_budget`. Ships the channel behind `BUDGET_ENGINE_ENABLED`.
- **Phase B** (~½ day): ClearGov/OpenGov fingerprint auto-detect + `budget_url` on target +
  dialog pre-fill (reuses the site-metadata machinery).
- **Phase C** (optional): JS-render fallback for ClearDoc-style sources with no PDF export.

## 9. Open decisions (need your call before building)

1. **Scope of platforms for v1** — PDF + ClearGov + OpenGov enough, or must we also cover
   Socrata / self-hosted at launch?
2. **Whole budget vs. specific sections** — scan the entire budget, or only the sections
   most likely to name AI (IT / capital / non-departmental)? Section-scoping cuts cost and
   noise but risks missing a line.
3. **Cadence** — budgets are annual. One-shot on demand (like agendas) is likely enough; do
   we also want an annual auto-refresh when a new budget is detected?
