# SB 1964 Framework Lens — Grounded Design (ready to build)

**Status:** DESIGN, grounded in primary/authoritative sources. Build is an ADDITIVE config
task per the `add-compliance-framework` skill — no engine change. Execute in a focused pass
using `safe-edit` for SCHEMA_DEFINITION.json.

---

## 1. What SB 1964 actually is (researched, cited — not from memory or a competitor)

Texas **SB 1964** (89th Leg., signed June 20 2025, effective **Sept 1 2025**) amends the
**Government Code**. It directs the **Department of Information Resources (DIR)** to, by
rule, establish an **AI system code of ethics** for **state agencies AND LOCAL GOVERNMENTS**
that procure, develop, deploy, or use AI, and requires agencies to **inventory their AI
systems and assess associated risks** as part of IT strategic planning.

The code of ethics must address: **human oversight, fairness, transparency, data privacy,
accountability, and regular evaluation**, and must **align with the NIST AI RMF 1.0**. It
adds definitions including *AI system, consequential decision, controlling factor,
heightened scrutiny AI system, principal basis*.

**Why this is the highest-fit extension:**
- It regulates **local governments** — your exact buyer's own obligation.
- It **mandates an AI inventory** — the artifact your discovery engine already produces.
- Its ethics code **must align to NIST AI RMF** — which is the spine your 14 controls are
  already mapped to. So the crosswalk is largely one-to-one at the function level.

**Sources:**
- Senate Research Center bill analysis (official): capitol.texas.gov/tlodocs/89R/analysis/pdf/SB01964S.pdf
- Jackson Walker, "Texas 89th Legislature: Key AI Legislation": jw.com/news/insights-texas-89th-legislature-ai/
- Holland & Knight, "Texas Enacts Comprehensive AI Governance Laws": hklaw.com/en/insights/publications/2025/06/texas-enacts-comprehensive-ai-governance-laws

---

## 2. Proposed control crosswalk (14 Safe-Harbor controls → SB 1964 ethics-code dimensions)

Mapped at the **dimension/objective level** (defensible; not inventing sub-clauses).
Because SB 1964's code must align to NIST and our controls carry a `nist_ref`, the mapping
rides the existing NIST spine. Overlap graded honestly.

| Control (function) | SB 1964 dimension | Overlap | Rationale |
|---|---|---|---|
| SH-GOV-01..04 (Govern: policy, roles, accountability) | **Accountability**, code-of-ethics adoption | **strong** | SB 1964's core ask is a governed, accountable AI program |
| SH-MAP-01..03 (Map: inventory, context, risk categorization) | **AI inventory + risk assessment** (the statutory mandate) | **strong** | SB 1964 *requires* the inventory our discovery produces |
| SH-MEA-01..03 (Measure: testing, monitoring) | **Regular evaluation**, **fairness** | **strong / partial** | evaluation strong; fairness/bias partial (we assess presence & disclosure, not model bias) |
| SH-MAN-01..04 (Manage: mitigation, response, oversight) | **Human oversight**, response | **strong** | oversight & cure workflow map directly |
| (disclosure controls) | **Transparency** | **strong** | overlaps TRAIGA disclosure we already assess |
| — | **Data privacy** | **partial/weak** | SB 1964 references it; our platform does not assess privacy controls — grade honestly, do not paper over |

Final control-by-control grades get **counsel review** before any compliance
representation (see caveats).

---

## 3. Build steps (additive only — per the skill's contract)

1. **`SCHEMA_DEFINITION.json` → `Safe_Harbor_Module.controls[]`:** add a `sb1964_ref` to
   each of the 14 controls (dimension name + overlap grade). **Use `safe-edit`** — recover
   from git, edit in /tmp, copy, verify byte-for-byte (this file truncated once this
   session).
2. **Framework registry** entry: `id: sb1964`, `name: "Texas SB 1964 — Government AI Code
   of Ethics"`, `version: "89R (2025)"`, `source_citation`, `jurisdiction: "TX"`,
   `mandatory: true`, `default_enabled: true` (it applies to every TX municipal target —
   unlike Colorado/ISO which ship disabled).
3. **`core/settings.py` → SETTABLE:** `FRAMEWORK_SB1964_ENABLED` (bool → auto-renders as a
   Settings switch). Default on for TX.
4. **Lens (`components/SafeHarborPanel.vue`):** add SB 1964 to the framework selector —
   re-labels/re-groups the SAME control results. No new evaluation.
5. **Alignment Statement (`api/routes/safeharbor.py`):** an SB 1964 variant of the docx
   that speaks the ethics-code dimensions and cites the statute + DIR rulemaking.
6. **Do NOT touch `evaluate_profile` or the evaluators.** The evidence is shared; the lens
   is a projection. If you're editing an evaluator, you're duplicating the assessment.

## 4. Caveats to print where the reader sees them (the honesty IS the product)
- This crosswalk is for **design and positioning, not legal advice**; mappings need
  **counsel review** before any compliance representation.
- Mapped at the **dimension/objective level**; DIR's implementing **rules were still being
  developed** — the code-of-ethics specifics will firm up as DIR rulemaking finalizes, so
  the lens must be revisited when the rules publish.
- **Data-privacy** overlap is honestly `partial/weak` — the platform does not assess
  privacy controls. A weak cell is information, not a gap to hide.

## 5. Verify + ship
- Schema still parses; `evaluate_profile` returns the **same** satisfied/unsatisfied set
  (proof the engine is untouched); a disabled framework never appears in a city's view.
- Ship via `ship-it`. Frontend deploys too (panel touched). Run `deploy-watch` after — and
  **watch that "Validate env.yaml" step**, now that the hardening guards it.

---

**Why this is teed up, not stalled:** the hard part of a compliance feature is the grounded
mapping and scope — done here, with sources. The remaining work is a mechanical additive
edit the skill fully specifies. Recommend executing as the next focused pass so the schema
gets `safe-edit` care.
