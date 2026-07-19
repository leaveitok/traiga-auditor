# Vendor Enrichment PoC — Citibot (2026-07-13)

> ⚠ **STATUS: RESEARCH ARTIFACT — NOT IN PRODUCTION.** Findings only; no code was built from this document.

Purpose: measure how much of a vendor governance profile can be **auto-populated from
public sources with citations** vs. how much must stay manual attestation — before we
commit to building an enrichment pass. Vendor: **Citibot** (municipal AI chatbot).
Method: live fetch of Citibot's own pages + web search of certification registries. No
fabrication — every value below is either quoted-with-source or marked unknown.

## Tier 1 — Statutory exposure (deterministic, no lookup needed)

| Field | Value | Basis |
|---|---|---|
| Function | chatbot / virtual assistant | observed by scanner |
| TRAIGA exposure | EXT-DISCLOSURE-PRESENCE/TIMING/CLARITY (§ 552.051) + EXT-PRIVACY-POLICY-04 | function → rule map |

Reliable, zero research. This is the part that never needs a vendor lookup.

## Tier 2 — Auto-filled from public sources (with citations)

| Fact | Value (as published) | Source | State |
|---|---|---|---|
| AI ethics posture | Publishes an AI Ethics Commitment (safety, privacy, transparency, bias mitigation) | citibot.io/ai-ethics-commitment | documented |
| Governance affiliation | "proud member of the GovAI Coalition" | ai-ethics-commitment | documented |
| Knowledge grounding (vendor claim) | "generative AI relies exclusively on information available on the customer's website" | ai-ethics-commitment | **vendor-stated** |
| Privacy policy | Published | citibot.io/privacy-policy | documented |
| Data retention | "All Visitor Personal Information will remain in Citibot databases for an **indefinite period of time**" | privacy-policy | documented ⚠ |
| Deletion | "Deleting a Citibot account will **not remove** a Visitor's Personal Information or documents" | privacy-policy | documented ⚠ |
| Third-party advertising | May share aggregate demographic/preference data with third-party advertisers | privacy-policy | documented ⚠ |
| Do-Not-Track | "Sites do not respond to… 'do not track' signals" | privacy-policy | documented |
| Company domicile | Charleston, SC, USA | site footer | documented |

**Critical caveat the enrichment must surface, not hide:** Citibot's privacy policy is
explicitly scoped to *"Citibot-owned websites… Visitors of the Sites"* — i.e., people
browsing citibot.io — **not** necessarily the resident chat data flowing through a city's
deployed bot. So the ⚠ clauses (indefinite retention, no deletion, ad sharing) may govern
the wrong data subject. Auto-enrichment can *pull and cite* these, but a human/legal
reviewer must judge whether they apply to the municipal deployment. It is a research
accelerator, **not** an auto-attestor.

## Tier 3 — Stayed UNKNOWN (not publicly confirmable → attest)

| Fact | Result |
|---|---|
| SOC 2 Type II | Not found in search or on-site → **unknown** |
| FedRAMP / StateRAMP authorization | No registry listing surfaced → **unknown** |
| Resident-data handling in a city deployment | Not addressed by the public site policy → **unknown** |
| Data residency (where resident data is stored) | Not published → **unknown** |
| Model training on resident inputs | Undisclosed (grounding claim ≠ training statement) → **unknown** |
| DPA / sub-processors | Not public → **unknown** |

## Verdict — ROI of an enrichment pass

- **What it saves:** the gather-and-read labor. It reliably harvests policy/ethics/trust
  URLs, the GovAI-Coalition signal, and flags notable clauses (indefinite retention, no
  deletion, ad-sharing) with citations — the raw material a reviewer would otherwise hunt
  for by hand. Registry lookups (FedRAMP/StateRAMP/CSA STAR) auto-run per vendor.
- **What it does NOT do:** confirm the assurances that actually matter in a compliance
  review. SOC 2 / FedRAMP / StateRAMP and resident-data handling were **not** publicly
  answerable for Citibot; those stay manual. And the auto-pulled policy may not even govern
  the relevant data flow — requiring human/legal judgment.
- **Net:** enrichment turns a blank profile into a **cited draft + a short, targeted gap
  list**, cutting research time meaningfully — but it cannot replace the vendor security
  questionnaire, and it must label everything **vendor-stated / scope-limited / unverified
  candidate** so a claim is never laundered into a fact.

## Recommendation

Build enrichment as an **evidence-gatherer**, not an oracle:
1. Harvest + cite public policy/ethics/trust URLs and notable clauses (with scope flags).
2. Auto-check certification **registries** (FedRAMP Marketplace, StateRAMP, CSA STAR) —
   these are authoritative and the highest-value auto-confirmable facts when present.
3. For everything unresolved, **auto-generate the targeted vendor questionnaire** (the exact
   short gap list) pre-filled with what we found — so the human sends a form, not a research
   project.
Everything stays `unverified_candidate` until a person confirms. That keeps the no-fabrication
rule intact and is more defensible than any black-box vendor "risk score."

Sources: https://www.citibot.io/ai-ethics-commitment · https://www.citibot.io/privacy-policy
