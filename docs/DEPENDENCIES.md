# Third-Party Dependencies & Subscriptions

Last updated 2026-07-07. Everything the platform relies on outside our own
code, so ownership, billing, and risk are visible at a glance.
**No keys, tokens, or passwords appear in this document or anywhere in the
repo** — secret *names* are listed in ARCHITECTURE.md §6; values live only in
Cloud Run environment configuration.

## 1. Paid / account-based services (the subscription picture)

| Service | What we use it for | Billing model | Criticality | Failure behavior |
|---|---|---|---|---|
| **Google Cloud Platform** (project `traiga-auditor`) | Cloud Run (backend API + scan engine), Firestore (both databases), Cloud Logging, container registry | Usage-based (Cloud Run vCPU/memory with `--no-cpu-throttling`, Firestore ops, egress) | CRITICAL — the platform | API down; data unreachable |
| **Firebase** (same GCP project) | Hosting (dashboard), Authentication (Google sign-in / ID tokens) | Spark/Blaze usage-based; Hosting + Auth effectively free at current scale | CRITICAL | Dashboard down / no logins |
| **GitHub** (`leaveitok/traiga-auditor`) | Source of record; Actions CI → Cloud Run backend deploys | Free tier currently (Actions minutes) | HIGH | Can't deploy backend; code safe locally |
| **Residential scan proxy** (ScraperAPI-style; wired via `SCAN_PROXY_URL`) | WAF-escalation tier of the crawler for cities that block datacenter IPs | Subscription + per-request; **cost control:** confirmed-WAF cities are excluded from bulk runs and scanned on demand only | MEDIUM | WAF cities fall back to `scan_failed` (fail-secure) + manual Deep Scan path still works |
| **Google Sheets API** | Legacy/rollback storage (`GOVERNANCE_STORE=sheets`) + original data plane | Free (service account) | LOW (rollback only) | Rollback path unavailable |
| **Google Workspace / Gmail account** | Owner identity, ADMIN_EMAILS bootstrap | Existing | HIGH (recovery) | Admin lockout risk — keep recovery current |

Renewal/ownership notes: all services are bound to the owner's Google/GitHub
identities. Before the TAGITM pilot, move billing to an organization account
and add a second owner for continuity.

## 2. Scanned-vendor ecosystem (NOT dependencies)

Citibot, CivicPlus, Repd, Munibit, Granicus, ElevenLabs, WhitegloveAI, etc.
appear throughout the product as *fingerprint targets* — AI vendors whose
widgets we detect on city websites. We have no commercial relationship with
them; nothing breaks if they change (except a signature may need updating —
that's the network-effect flywheel, see ROADMAP).

## 3. Backend open-source libraries (pip, `backend/requirements.txt`)

| Library | Role | Note |
|---|---|---|
| fastapi / uvicorn / pydantic | API framework | pydantic `extra='forbid'` enforces Sentinel metadata-only ingest |
| playwright **==1.44.0** | Browser engine for crawling | PINNED to match Docker base image `mcr.microsoft.com/playwright/python:v1.44.0-jammy` — a `>=` here broke Cloud Run on 2026-07-04 |
| playwright-stealth | WAF/bot-detection mitigation | |
| requests / beautifulsoup4 | Static-crawl fallback tier | |
| google-cloud-firestore | Primary storage | |
| google-api-python-client / google-auth | Sheets legacy store | |
| firebase-admin | ID-token verification | |
| python-docx | All generated legal documents (reports, Alignment Statement, AG Response Package, Cure Statement, AI Use Policy) | |
| jsonschema | Schema validation | |
| slowapi | Rate limiting (in-memory; no Redis at MVP) | |
| apscheduler | 24h scheduled scans | |
| pytest / httpx | Tests (local; sandbox uses `tests/shims/`) | |

## 4. Frontend open-source libraries (npm, `frontend/package.json`)

| Library | Role |
|---|---|
| vue 3 / vue-router / pinia | SPA framework, routing, state (layering rule: components → stores → GovernanceService → axios) |
| vuetify 3 + @mdi/font | UI components + icons |
| axios | HTTP with auth interceptors (per-request Firebase token + 401 retry) |
| firebase (JS SDK) | Auth client |
| vite (+ plugin-vue, plugin-vuetify) | Build — the JS quality gate |

## 5. Development-time services

| Tool | Role |
|---|---|
| Claude (Cowork) + Claude in Chrome | Primary development agent; Deep Scan execution path for WAF cities |
| Windows dev machine | Only environment that can `git push` and run `.bat` deploys (PowerShell is blocked by policy — always cmd.exe/.bat) |

## 6. Risk summary

- **Single-provider concentration:** GCP/Firebase carry everything. Accepted
  at this stage; Sheets rollback exists for data-plane emergencies.
- **Proxy dependency:** only affects WAF-protected cities; fail-secure plus
  Deep Scan covers the gap manually.
- **Playwright/Docker version coupling:** the one true version pin in the
  system — never loosen it (see requirements.txt comment for the incident).
- **Account continuity:** single-owner Google/GitHub identities are the
  biggest organizational risk; fix before pilot onboarding.
