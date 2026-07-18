# Agenda Deep-Text Detection — Design / Scope (DRAFT for review)

Status: proposed, not built. Author: architecture pass, 2026-07-13.
Sibling of `AGENDA_ENGINE_DESIGN.md` and `DISCOVERY_EXPANSION_DESIGN.md`.

## 1. Problem — the title-only ceiling

The agenda channel gates council/EDC items by an award-keyword screen on the item
**title**, then runs the AI-keyword screen over the extracted vendor/product. It flags
AI only when the item is *named* as AI. It cannot see AI embedded in a generically
named procurement.

Verified example (live Legistar, McKinney): a 12-month scan processed **262** award-
gated items and matched **0** AI — a true negative for *explicitly-labeled* AI, but a
miss for *embedded* AI:

- MatterFile `25-3382`, MatterId `29386` — *"…Purchase of Smart Truck Camera
  Technology…"*. A smart truck camera is almost certainly computer-vision AI, but
  neither the `EventItemTitle` nor the fuller `MatterTitle` names it as AI, so the
  conservative title screen (correctly) does not assert it.

Raising recall on embedded AI **without** eroding precision or flooding the human-review
queue is the goal.

## 2. Goals / non-goals

**Goal:** for award items the title screen did NOT already flag, screen *richer text*
(matter title/body/attachments) for AI signal, surfacing document-derived candidates as
*weaker, clearly-labeled* signals for human review.

**Non-goals:** no change to Tier-1 title behavior (additive, backward-compatible); not
the website compliance scanner; Legistar first (PDF/other portals reuse the same seam).

## 3. Design — two-tier detection

- **Tier 1 (today):** award gate + AI screen on the item TITLE. Fast, free, high precision.
- **Tier 2 (new, opt-in):** for award items NOT already AI-flagged in Tier 1, fetch
  richer text and run the existing AI-keyword regex over it. Only text-level hits become
  `procured_ai_candidate`s, marked document-derived + lower confidence.

**Cost property (the point):** Tier 2 runs only on the *residual* of award items (already
a small subset) that Tier 1 missed. The **free regex** over richer text does the
surfacing; the **LLM** (vendor/product extraction) runs only on Tier-2 hits — never on
all items. So added cost scales with document fetches, not with LLM calls.

## 4. Enrichment sources (Legistar; cheapest → richest; verified live)

1. **MatterTitle** — fuller than `EventItemTitle`, always present, one field
   (`EventItemMatterId` → `/v1/{client}/matters/{id}`). Near-free. *Marginal* gain — note
   it still does NOT catch "Smart Truck Camera" (title says nothing about AI).
2. **Matter attachments** — staff-report / contract PDFs via
   `/v1/{client}/matters/{id}/attachments` (`MatterAttachmentHyperlink`) → the existing
   `pdf_bytes_to_text` path. **Richest** and where "Smart Truck Camera → AI-based object
   detection" would actually surface — but **availability is inconsistent** (verified:
   matter 29386 returned no attachments) and PDF fetch+parse is the cost driver.
3. *(Optional)* Matter legislative/EX text — availability varies by city.

**Default:** Tier 2 uses source (1) always (near-free); source (2) only when
`AGENDA_DEEP_TEXT_ATTACHMENTS=true`. Must degrade gracefully when a matter has neither.

## 5. Cost controls (all env, OFF by default)

- `AGENDA_DEEP_TEXT_ENABLED` (bool, default false) — master switch.
- `AGENDA_DEEP_TEXT_ATTACHMENTS` (bool, default false) — allow PDF attachment fetch/parse.
- `AGENDA_DEEP_TEXT_MAX_ITEMS` (int) — hard cap of items deep-scanned per run.
- Reuse `AGENDA_FETCH_CONCURRENCY` for parallel matter/attachment fetches.

## 6. Provenance & confidence (governance-first)

A Tier-2 hit is a **weaker** signal (the title did not name AI). It must read differently:

- provenance stays `discovered_agenda`; add evidence `ai_signal_source: "document"` (vs
  `"title"`), plus the source URL of the document that triggered it.
- lower `match_confidence`; reviewer-facing note: *"AI signal found in the item's attached
  document, not the agenda title — verify."*
- Candidate discipline preserved: always human-review, never asserted, never a violation.

## 7. Architecture placement (existing principles unchanged)

- **Fetch (I/O):** extend `core/discovery/agenda_fetch.py` —
  `fetch_matter_text(client, matter_id, *, want_attachments, fetch_json, fetch_bytes)`
  returning richer text. `fetch_json`/`fetch_bytes` injectable → testable offline.
- **Pure:** `engine/collectors/agenda.py` — `screen_text_for_ai(text, schema) -> [kw]`
  reusing the existing `ai_keywords` (word-boundary). No new matcher, no new schema.
- **Orchestrator:** `core/discovery/agenda_source.py` — after Tier-1 normalize, take the
  non-flagged award items, run Tier 2, merge hits as candidates via the same repo path.
- Engine stays storage-agnostic; no engine↔repo coupling; no *required* frontend change
  (hits appear as needs-attestation like today). Auth placeholders unchanged.

## 8. Testing (sandbox-runnable, no live HTTP/LLM)

- Pure `screen_text_for_ai`: title-miss + document-hit cases.
- `fetch_matter_text`: injected `fetch_json`/`fetch_bytes` fixtures (matter JSON + fake
  PDF bytes).
- Orchestrator: `MockRepo` + fake extractor — assert a document-only AI item becomes a
  candidate with `ai_signal_source=document` and lower confidence.

## 9. Phasing

- **Phase A** (~½ day): Tier-2 with **MatterTitle** only. No PDF cost. Small lift; ships
  the seam + flags behind `AGENDA_DEEP_TEXT_ENABLED`. (Note: will NOT catch Smart Truck
  Camera — that needs Phase B.)
- **Phase B** (~1–2 days): attachment PDF fetch/parse + caps. The real recall gain; the
  cost driver. Depends on Phase A seam.
- **Phase C** (optional): surface a "N found in documents" count/badge in the agenda
  result dialog.

## 10. Open decisions (need your call before building)

1. **Precision appetite.** Is a *"document-derived, verify"* candidate acceptable in the
   review queue, or must every flag be title-grade? (Decides whether Phase B ships.)
2. **Attachment cost ceiling.** OK to fetch/parse up to N staff-report PDFs per city per
   run? Suggested default N = 25.
3. **Extract or just flag.** For a document hit, also LLM-extract vendor/product (nicer
   inventory row, more tokens) or just flag the item for review (cheaper)?
