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
| `DISCOVERY_EXPANSION_DESIGN.md` | 🟡 PARTIAL | Identity substrate, procurement + agenda channels **shipped**; OAuth/shadow-AI channel shipped **export-first only** (no live tenant sync yet). |
| `INVENTORY_SPEC.md` | ✅ SHIPPED | AI asset inventory model, provenance, lifecycle. |
| `USER_GUIDE.md` | 📘 REFERENCE | End-user manual (v1.2) for the shipped product. |
| `AGENDA_DEEP_TEXT_DESIGN.md` | ⚠️ DESIGN ONLY | Reading agenda item *documents* (not just titles) to catch embedded AI. |
| `BUDGET_CHANNEL_DESIGN.md` | ⚠️ DESIGN ONLY | Adopted-budget discovery channel (ClearGov/OpenGov/PDF). |
| `BUNDLED_AI_FEATURE_DESIGN.md` | ⚠️ DESIGN ONLY | Detecting AI features bundled into tools cities already own. |
| `VENDOR_ENRICHMENT_DESIGN.md` | ⚠️ DESIGN ONLY | Auto-populating vendor governance facts from cited public sources + registries. |
| `OAUTH_DISCOVERY_DESIGN.md` | 🟡 PARTIAL | Phases 0–1b **shipped** (export-first, dry-run-by-default backend, upload dialog). Phase 2 live Microsoft sync, Phase 3 Google Reports API, and Phase 4 scheduled re-sync **not built**. |
| `INSTALL_OAUTH_MICROSOFT.md` | ✅ SHIPPED | Step-by-step Entra setup for a city IT admin. **Two methods**: run the script, or Graph Explorer browser-only for shops where endpoint protection blocks PowerShell. Script is downloaded from the dashboard with a server-computed checksum (no hardcoded hash). Covers `Unblock-File` / execution policy. |
| `INSTALL_OAUTH_GOOGLE.md` | ❌ NOT WRITTEN | Google Workspace equivalent. Needed before Lewisville can run the Google side. |
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
