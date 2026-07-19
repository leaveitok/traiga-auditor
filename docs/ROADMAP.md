# Product Roadmap — Path to Market Leadership

Last updated 2026-07-18. Horizon framing per the CIO's practice. The sequence
is chosen so every phase strengthens the demo-led sales motion: the sales
demo IS the product (scan a prospect's site before the meeting; show them AI
they didn't know they had — proven live on Denton, Grand Prairie).

## Strategic position

- **Category:** GRC for AI — for organizations that *consume* AI (vendor
  chatbots, embedded tools, staff LLM use), not build it. Incumbents (IBM
  watsonx.governance, ServiceNow, OneTrust) and dedicated platforms (Credo,
  Holistic, Trustible) serve model builders and enterprises at ~$50K+/yr.
- **Beachhead:** Texas municipalities under HB 149 / TRAIGA; distribution via
  TAGITM (~1,200 municipalities).
- **Moat:** discovery-fed compliance across FOUR live channels — outside-in
  scanner, inside-out Sentinel, procurement files, and council agendas —
  plus operational 60-day cure tracking and statute-generated legal artifacts
  (§ 552.103/.104/.105) that document-pack competitors cannot produce from live
  evidence. Each channel resolves to one canonical registry row, so a tool found
  three ways is one asset with a three-source evidence trail.
- **Competitive note (CloudEagle.ai, reviewed 2026-07-13):** the enterprise
  SaaS/AI-governance leaders use the same architecture (many signals → one AI
  catalog), which validates the design. Their strongest signals are SSO + finance —
  evidence that the OAuth channel (H2) is the right next build. Deliberately NOT
  copied: prompt-layer blocking (we are an out-of-line observer), token-spend
  optimization, and opaque vendor "risk scores".

## H1 — Prove (0–60 days)

Exit criteria: platform credible at 50+ cities; a second (non-Lewisville)
agency using it unassisted.

| # | Deliverable | Status |
|---|---|---|
| 1 | Attest first registry assets (Denton/Repd, Lewisville/Citibot, Grand Prairie/ElevenLabs) | OPEN — do first |
| 2 | Durable audit-run state in Firestore | **DONE** — shared `run_state` doc, atomic `claim_run_slot`, heartbeat lease (`AUDIT_LEASE_STALE_SECONDS`) |
| 3 | Bulk city import (CSV) for TAGITM scale | **DONE 2026-07-07** |
| 4 | Sentinel view auto-refresh + webextension `hooking.js` `chrome.runtime?.id` guard + city-tag config for usage sync | OPEN |
| 5 | Onboard first real agency + users in Admin Console | OPEN |
| 6 | CI test gate in deploy.yml | **DONE** — `deploy.yml` runs pytest as a `test` job and the deploy job has `needs: test`, so a red test blocks the Cloud Run deploy. The frontend half is gated by the CI `vite build` in `deploy_frontend.yml` |

## H2 — Expand (60–180 days)

Exit criteria: the registry is the daily-use surface; TAGITM cohort
referenceable; crosswalks make the platform legible to auditors outside Texas.

| # | Deliverable | Status |
|---|---|---|
| 1 | Sentinel-fed usage assets (inside-out joins outside-in) | **DONE 2026-07-07** (city-tag rollout pending, H1-4) |
| 2 | Framework crosswalks: NIST AI RMF + ISO/IEC 42001 | **DONE** — Safe Harbor / Municipal AI Profile v1.0 (14 controls) with a framework registry of 3 lenses (NIST AI RMF, TRAIGA, ISO/IEC 42001). ISO ships built-but-disabled behind `FRAMEWORK_ISO_42001_ENABLED`; the panel re-labels the SAME assessment per lens ("assess once, comply many"). Colorado SB 24-205 is crosswalked on paper only |
| 3 | Compliance report v2: attestation coverage % + Safe Harbor band for council packets | PARTIAL — Alignment Statement + CID package exist; council-report integration open |
| 4 | Inventory v1.1: CSV export, per-asset review reminders | OPEN |
| 5 | Vendor signature growth via sweeps (network effect) | ONGOING — **11 vendors** (added: repd, elevenlabs_convai, frase, uneeq, plus the fail-secure `unknown_chatbot` structural candidate). The AI-keyword list is now 27 terms including a curated public-safety cluster (ALPR, gunshot detection, predictive policing) chosen for precision |
| 6 | TAGITM pilot cohort: 10–20 cities, standard onboarding runbook | OPEN |
| 7 | Vendor AI risk module | **PARTIAL** — the sourced `Governance_Profile` shipped: deterministic function→statute exposure, vendor facts recorded only with a `source_url` (else `not_published`/`unknown`), and **deliberately no risk score**. Automated enrichment + the auto-generated vendor gap questionnaire are SCOPED but not built (`docs/VENDOR_ENRICHMENT_DESIGN.md`) |
| 8 | Council-agenda discovery at scale | **DONE** — Legistar/PDF/paste; server-side date window; concurrent per-meeting fetch + one LLM call per meeting (fits Cloud Run's 300s cap); in-app "which extractor ran" badge |
| 9 | Site-metadata auto-capture + provenance/deployment badges | **DONE** — scans learn agenda platform/slug, CMS, privacy URL as unverified candidates; the agenda slug pre-fills; every inventory row shows its source channel and *Live on site* vs *Procured · verify* so implementation timing is never misread as non-compliance |
| 10 | Responsive UI (phone/tablet) | **DONE** — overlay nav below 960px, tables stack below 600px, breakpoint pinned explicitly |

## H3 — Dominate (180–365 days)

Exit criteria: revenue outside Texas; revenue outside government; the
registry is the system of record customers cite in audits.

1. Multi-state rule modules (Colorado AI Act, EU AI Act annexes) — same
   engine, new statutes as schema modules.
2. Private-sector beachheads: hospitals (HIPAA), banks (model-risk adjacent),
   school districts (COPPA/FERPA) — identical scan+registry motion.
3. Sentinel service split (own Cloud Run service account) so "Sentinel
   identity cannot read scanner data" is fully true.
4. Procurement module: AI clauses/questionnaires tied to registry entries.
5. Partner/reseller channel via municipal leagues in other states (replicate
   the TAGITM playbook).

## Scoped but NOT built (design docs only — see `docs/DOC_STATUS.md`)

Each has an open-decisions list awaiting a call; none is in production:
- **Agenda deep-text extraction** — read item *documents*, not just titles, to catch AI
  embedded in generically named buys ("Smart Truck Camera"). Recommended to HOLD: low ROI
  against review-queue noise; OAuth is the better use of the same week.
- **Adopted-budget channel** — ClearGov/OpenGov/PDF; reuses the PDF path + matcher +
  site-metadata fingerprints.
- **Bundled vendor-AI-feature detection** — flag AI that incumbent vendors (Tyler,
  CivicPlus, Granicus, Microsoft) switch on inside tools a city already owns.
- **Automated vendor enrichment** — pre-fill the governance profile from cited public
  sources + certification registries, and auto-generate the vendor gap questionnaire.

## Strategy threads not yet opened (flagged in every handoff)

- **Pricing/packaging** (per-city vs per-agency tiers) — never discussed.
- **TAGITM pilot pitch deck** — the sweep scorecard + cure countdown +
  attested inventory + Safe Harbor band are its spine.
- **TAGITM branding of the Municipal AI Profile** — deferred until cleared
  with the association (one-string schema change when approved).
- **Directory presence:** submit TRAIGA Auditor to aicompliancevendors.com
  (the definitive TRAIGA tools ranking lists six enterprise vendors and no
  scanner).
