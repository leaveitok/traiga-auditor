# OAuth / Shadow-AI Discovery — Design / Scope (DRAFT for review)

> ⚠ **STATUS: DESIGN ONLY — NOT IN PRODUCTION.** Nothing described in this document is
> built or deployed. It is a proposal for review.

Status: proposed, not built. Author: architecture pass, 2026-07-18.
Pilot: **City of Euless (Microsoft shop)**; **Lewisville (Microsoft + Google)**.
Read alongside `DISCOVERY_EXPANSION_DESIGN.md` and the `add-discovery-channel` skill.

## 1. Why this is the flagship channel

The website scanner finds AI the city *published*. Procurement and agendas find AI the city
*bought*. **Neither finds the AI an employee signed up for without asking IT** — a Copilot
add-in, a note-taker with calendar access, an AI plugin granted read access to Drive. That
consent event lives in the identity provider, and nowhere else. For a CIO this is the
question that actually keeps them up at night.

Feeds the existing registry as `provenance=discovered_oauth`. The `oauth_app_ids` alias
placeholder ALREADY exists in `AI_Tool_Catalog` — the substrate was built for this.

## 2. TWO FRONT DOORS — export-first, credentials second (the de-risking decision)

The naive design asks a city for standing directory credentials on day one. That is a
procurement and trust hurdle that will stall pilots, and it front-loads all the risk.
**The same pure normalizer accepts records from either door**, so we ship the zero-trust one
first:

**Door A — customer-run export (DEFAULT, ships first).**
We publish a read-only **script** — not an app, not an agent, nothing of ours installed.
The city's admin runs it *in their own environment*, it writes a JSON file, **they open the
file and see exactly what would leave**, then upload it to the dashboard — reusing the
existing Import-Procurement upload path.
- **Microsoft: no credential is created at all.** The admin runs it under their OWN
  interactive session (`Connect-MgGraph` with read scopes); there is no app registration, no
  client secret and no standing grant — the token dies with the session. Nothing to give us,
  nothing to revoke.
- **Dependency, stated plainly:** the Microsoft script needs Microsoft's own official
  `Microsoft.Graph` PowerShell module (Microsoft-published and Microsoft-signed). That is
  standard M365 admin tooling — it is not our code running on their machine.
- **Integrity: NOT Authenticode-signed.** We do not hold a code-signing certificate, so we do
  not claim one. We publish the plain-text source in the repo plus a **SHA-256 checksum** so
  the admin can verify the file they received is the file we published — and read every line
  before running it.
- Zero credentials shared. Zero standing access. No security review required to try it.
- Point-in-time snapshot, not monitoring — the honest trade.
- Precedent: this is what CloudEagle's "Universal Connector" does for sources without APIs.

**Door B — live read-only credentials (OPT-IN upgrade).**
For cities that want continuous discovery, per-tenant credentials enable scheduled sync.
Offered only after Door A has proven value.

**Sequence matters:** prove the finding at near-zero risk, then earn the right to ask for
standing access.

## 3. What we read (verified against current vendor docs, 2026-07-18)

**Microsoft Entra (Graph)**
- `GET /oauth2PermissionGrants` — delegated permission grants, *created when a user consents
  to an app*. This IS the shadow-AI signal.
- `GET /servicePrincipals` — app display name, publisher, homepage.
- Permissions: read-only application permissions with admin consent. Writes require the
  separate `.ReadWrite.All` variants, which we never request — **so Entra itself returns 403
  on any write attempt, regardless of our code.** Microsoft's own guidance is to prefer
  narrow permissions over broad `Directory.*`; request the narrowest set that works.

**Google Workspace (Admin SDK)**
- **Primary (default): Reports API** `activities.list?applicationName=token` with scope
  **`admin.reports.audit.readonly`** — a genuinely `.readonly` scope that CANNOT modify
  anything. OAuth authorization/revocation events over time.
- **Optional (opt-in): Directory API** `GET /users/{userKey}/tokens` (`tokens.list`) for
  richer per-app detail. **Disclosure:** its scope `admin.directory.user.security` is **NOT
  strictly read-only** — the same scope also permits `tokens.delete`. We never call delete,
  but the city is granting a scope that *could*. Default to the Reports API; let the customer
  decline the Directory scope.
- Auth: service account with domain-wide delegation (Admin console → Security → API Controls
  → Domain-wide Delegation).

**Verification the customer can do without trusting us:** every call we make appears in their
own Entra / Google Admin audit logs. "Check your logs" beats "trust our code."

## 4. Credential model (Door B): customer-owned, instantly revocable

The city creates the app registration / service account **in their own tenant**, grants
read-only scopes, and hands us a credential they can revoke in seconds. Rejected alternative:
our multi-tenant app that cities consent to — easier onboarding, but one compromise reaches
every tenant and the customer cannot independently kill it. Wrong posture for government.
Future upgrade: workload identity federation, removing stored secrets entirely.
Storage: per-tenant secret in Secret Manager (see the `cloud-setup` skill).

## 5. Privacy posture — this is employee-monitoring data

- **Default: app-level aggregates** — which app, which scopes, how many users. NOT who.
- **User-level identities are opt-in**, agency-scoped, mirroring Sentinel's fail-secure rule
  (untagged rows are platform-admin-only). Needed to actually revoke a grant, so it is a
  deliberate, permissioned reveal — never the default.
- Metadata only. We never read mail, files, or prompt content.

## 6. The signal worth surfacing: SCOPES, not a score

Report **"this app holds read access to Drive and Mail,"** not just "ChatGPT is connected."
The granted scopes are the governance fact. Add a scope→sensitivity table to
`SCHEMA_DEFINITION.json` (governance-as-code, extend by JSON; no code change). Consistent
with `Governance_Profile`: sourced facts, **no computed risk score**.

## 7. Architecture placement (project rules)

- **PURE:** `engine/collectors/oauth.py` — `normalize(grants, index, city)` → candidates via
  the identity resolver + `oauth_app_ids` aliases. No HTTP, no repo, no LLM. Serves BOTH doors.
- **I/O clients:** `core/discovery/oauth_microsoft.py`, `core/discovery/oauth_google.py` —
  `fetch_json` injectable so every test runs offline against recorded fixtures.
- **Orchestrator:** `core/discovery/oauth_source.py` — flag-gated (`OAUTH_DISCOVERY_ENABLED`),
  tenancy-scoped, merges via the existing `merge_discovered_assets`, audit-logged per run.
- **Route:** `POST /api/discovery/oauth` (platform/agency admin, city-scoped) + the upload
  path for Door A.
- **Frontend:** components → stores → GovernanceService. No component calls Axios.
- Engine stays storage-agnostic; auth placeholders on every governance read/write.

## 8. Because the pilot runs in a production tenant

- **DRY-RUN mode (default for the first run):** fetch and report WITHOUT writing to the
  registry. Euless sees the findings and approves before anything is persisted.
- **No writes on a partial fetch** (fail-secure — absence of evidence ≠ evidence of absence).
- **Per-tenant kill switch**; bounded concurrency + rate-limit backoff.
- One audit-log entry per run: actor, tenant, counts, dry-run flag.

## 9. Our own security posture (a city WILL ask)

True today: TLS everywhere (Hosting + Cloud Run); Firestore/Cloud Run encrypted at rest with
Google-managed keys; secrets in Secret Manager, never in the repo; `REQUIRE_AUTH=true` with
server-verified Firebase ID tokens; security headers (HSTS, nosniff, frame-deny,
referrer-policy, permissions-policy) shipped 2026-07-18.

**Gaps to state honestly before a pilot review:**
- **No SOC 2 and no penetration test.** If we ask a city for directory access, they will ask
  for ours. This is the strongest argument for Door A, which sidesteps the question entirely.
- No CMEK (Google-managed keys only) — some agencies require customer-managed.
- No Content-Security-Policy yet (deliberate: ship as `Report-Only` first; a wrong CSP
  breaks the app and the production build cannot be run locally).

## 10. Testing

- Pure `normalize` unit tests against **recorded fixtures** from both providers (no tenant).
- Client tests with injected `fetch_json` — offline.
- Orchestrator with `MockRepo`: dry-run writes nothing; partial fetch writes nothing;
  aggregates never carry user identities unless the flag is on.
- Fixture-based regression for scope→sensitivity mapping.

## 11. Phasing

- **Phase 0** (~1 day): schema (`oauth_app_ids` aliases + scope-sensitivity table), pure
  normalizer, fixtures. No network, no credentials.
- **Phase 1** (~1–2 days): **Door A** — export scripts + upload path + **Microsoft config
  manual**. Euless pilots with zero credentials shared.
- **Phase 2** (~2 days): **Door B** Microsoft live client + dry-run + Secret Manager wiring.
- **Phase 3** (~1–2 days): Google (Reports API first), proving both stacks at Lewisville.
- **Phase 4**: scheduled re-sync, UI polish, revoke-guidance (guidance only — we observe).

## 12. Deliverables still to write

- `docs/INSTALL_OAUTH_MICROSOFT.md` — click-by-click: app registration, exact permissions,
  admin consent, secret handling, how to revoke, how to verify in audit logs.
- `docs/INSTALL_OAUTH_GOOGLE.md` — service account, domain-wide delegation, exact scopes,
  how to revoke, how to verify.
- Both written for a city IT admin, not a developer, and both stating the read-only guarantee
  and what we never touch.

## 13. Open decisions

1. **Dry-run for Phase 1 only, or permanently opt-out-able?** (Recommend: dry-run default on
   the first run per tenant, always available.)
2. **User-level identities off by default?** (Recommend: yes — aggregates only until asked.)
3. **Google: Reports API only for v1**, deferring the Directory `tokens.list` scope? (Recommend
   yes — it keeps the ask strictly `.readonly`.)
4. Do we pursue SOC 2 now, or lead with Door A until revenue justifies it?
