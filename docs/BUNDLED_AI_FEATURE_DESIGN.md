# Embedded / Bundled AI-Feature Detection — Design / Scope (DRAFT for review)

Status: proposed, not built. Author: architecture pass, 2026-07-13.
Prompted by CloudEagle's "AI features activating silently inside tools you already own."

## 1. Why

A city rarely "buys AI." Its **incumbent vendors bolt AI onto products the city already
runs** — Tyler, CivicPlus, Granicus, Microsoft (Copilot), NEOGOV, etc. The feature turns
on, nobody declared it, and it may carry a live § 552.051 disclosure obligation. This is
the highest-signal, most municipal-specific discovery idea on the table: the AI is already
inside the stack.

## 2. Two detection modes (very different reliability — keep them separate)

- **A. OBSERVED (high precision, already partly built).** The website scanner detects the
  live AI widget/feature on the site (e.g., a Granicus/CivicPlus chatbot). We already do
  this via `AI_Vendor_Fingerprints`. The NEW value is *attribution*: label it as
  **"a feature of a tool you already own"** (the vendor is the city's CMS/agenda/permitting
  platform) rather than a net-new tool. Deployment badge: **Live on site** (real obligation).

- **B. ADVISORY (higher recall, must be labeled as NOT-a-finding).** The city is known to
  run vendor X (from a scan fingerprint, or from procurement/agenda provenance), and vendor
  X has *publicly shipped* an AI feature (from a curated, sourced table). We surface an
  **advisory candidate**: *"Your vendor {X} shipped AI feature {Y} on {date} — verify
  whether it is enabled and, if so, disclosed."* This is NOT evidence the city enabled it;
  it is a prompt to check. It MUST render as **"Vendor capability — verify enabled"**, never
  as a live violation. This is exactly the implementation-timing false-positive the
  provenance/lifecycle badges were built to prevent.

## 3. Governance-as-code — the vendor-feature table (sourced, candidate)

New schema block `Vendor_AI_Features`: a list of sourced entries, each an UNVERIFIED
CANDIDATE until confirmed (same discipline as fingerprints and the governance profile):

```
{ "vendor_id": "granicus",
  "feature_name": "…",
  "function": "chatbot",            // -> Governance_Profile.statutory_exposure
  "delivery": "bundled_in_product", // vs add-on / opt-in
  "announced_date": "YYYY-MM-DD",
  "disclosure_relevant": true,
  "source_url": "https://…",        // REQUIRED — no source, no entry
  "verification_status": "unverified_candidate" }
```

No entry without a `source_url`. The table is a curated, cited artifact — never inferred.

## 4. How it plugs into what exists (little new machinery)

- **Identity:** reuse `vendor_id` from `AI_Vendor_Fingerprints` / `AI_Tool_Catalog`.
- **Exposure:** map the feature's `function` through the new `Governance_Profile.
  statutory_exposure` for the "what obligation does this trigger" line.
- **Provenance/lifecycle:** Mode A = existing `discovered_scan` (Live on site). Mode B = a
  new provenance `discovered_vendor_feature` rendering as **"Vendor capability · verify
  enabled"** in the badge we just shipped — additive, no violation, no cure clock.
- **Cost:** effectively zero — table lookup against detected/known vendors. No LLM, no PDF.

## 5. Architecture placement

- **Pure:** `engine/collectors/vendor_feature.py` — `match_vendor_features(city_vendors,
  table) -> [advisory_items]` (pure, testable).
- **Orchestrator:** fold into the discovery merge; write Mode-B items as
  `discovered_vendor_feature` candidates. Flag-gated `VENDOR_FEATURE_ADVISORY_ENABLED`.
- **Schema:** `Vendor_AI_Features` block; add vendor-feature provenance to the badge map
  (frontend already structured for it).
- Storage-agnostic engine + candidate discipline preserved.

## 6. Testing

- `match_vendor_features` pure unit tests (city runs vendor with a shipped feature ->
  advisory; city without -> nothing).
- Integrity test: every `Vendor_AI_Features` entry has a `source_url`; every `function`
  resolves in `Governance_Profile.statutory_exposure`.

## 7. Phasing

- **Phase A** (~1 day): Mode A attribution — label scan-detected features as
  "vendor-owned," link to the governance profile. Pure precision, no new claims.
- **Phase B** (~1–2 days): the sourced `Vendor_AI_Features` table + Mode-B advisories
  behind a flag, rendered as "verify enabled."
- **Phase C** (ongoing): curate the table as vendors ship features (a natural TAGITM
  network-effect artifact — one sourced entry helps every city on that vendor).

## 8. Open decisions (need your call)

1. **Advisory mode on/off for v1.** Ship only Mode A (observed, high precision), or also
   Mode B (advisory, higher recall but requires the "verify enabled" framing)?
2. **Who curates `Vendor_AI_Features`.** Internal research with citations, or crowdsourced
   from the TAGITM network with a review step?
3. **Refresh cadence.** Vendors announce features continuously — monthly table review, or
   event-driven when a member reports one?
