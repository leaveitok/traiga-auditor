# Documentation Status Index

Quick answer to "is this doc describing something that actually exists?"

**Legend**
- ✅ **SHIPPED** — described behavior is built and deployed in production.
- 🟡 **PARTIAL** — some of it shipped; the rest is still a proposal (see the doc).
- ⚠️ **DESIGN ONLY — NOT IN PRODUCTION** — a proposal. Nothing in it is built.
- 🔬 **RESEARCH** — findings/PoC only; no code was built from it.
- 📘 **REFERENCE** — living reference material (architecture, ops, user guide).

Every ⚠️/🔬 doc also carries a banner at the top of the file itself, so the status
travels with the document. Grep for `NOT IN PRODUCTION` to list them.

| Doc | Status | Covers |
|---|---|---|
| `AGENDA_ENGINE_DESIGN.md` | ✅ SHIPPED | Council-agenda discovery: Legistar + PDF fetch, gating, LLM extraction, merge. Live. |
| `DISCOVERY_EXPANSION_DESIGN.md` | 🟡 PARTIAL | Identity substrate, procurement + agenda channels **shipped**; OAuth/shadow-AI channel **not built**. |
| `INVENTORY_SPEC.md` | ✅ SHIPPED | AI asset inventory model, provenance, lifecycle. |
| `USER_GUIDE.md` | 📘 REFERENCE | End-user manual (v1.2) for the shipped product. |
| `AGENDA_DEEP_TEXT_DESIGN.md` | ⚠️ DESIGN ONLY | Reading agenda item *documents* (not just titles) to catch embedded AI. |
| `BUDGET_CHANNEL_DESIGN.md` | ⚠️ DESIGN ONLY | Adopted-budget discovery channel (ClearGov/OpenGov/PDF). |
| `BUNDLED_AI_FEATURE_DESIGN.md` | ⚠️ DESIGN ONLY | Detecting AI features bundled into tools cities already own. |
| `VENDOR_ENRICHMENT_DESIGN.md` | ⚠️ DESIGN ONLY | Auto-populating vendor governance facts from cited public sources + registries. |
| `CITIBOT_ENRICHMENT_POC.md` | 🔬 RESEARCH | Live PoC measuring how much vendor data auto-fills vs stays manual. |
| `ARCHITECTURE.md` | 📘 REFERENCE | System architecture. |
| `FEATURES.md` | 📘 REFERENCE | Feature catalog. |
| `OPERATIONS.md` | 📘 REFERENCE | Runbook / operations. |
| `DEPENDENCIES.md` | 📘 REFERENCE | Dependency inventory. |
| `ROADMAP.md` | 📘 REFERENCE | Forward plan. |
| `PROJECT_BRAIN.md` | 📘 REFERENCE | Project context. |
| `README.md` | 📘 REFERENCE | Docs entry point. |

## Keeping this honest

When a ⚠️ design ships: (1) delete the banner from the top of that doc, (2) flip its row
here to ✅ SHIPPED, (3) do both in the same commit as the code. A design doc that silently
becomes reality is how documentation starts lying.
