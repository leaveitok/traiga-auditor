# Evidence Bundles — Design & Build Blueprint

**Status:** DESIGN ONLY — not yet built. Tracked in DOC_STATUS.md.
**Author:** Chief-of-Staff planning pass, July 2026.
**Owner decision captured:** ship BOTH a single tailored document and a robust
auditor package — implemented as *presets on one engine*, phased.

---

## 1. Why we are building this

Audience-tailored evidence bundles are the highest-value gap between us and the
one visible TRAIGA competitor (TXAIMS). The strategic point is not "a nicer report":
it is to become the city's **system of record for compliance evidence**, so a city
does not need a second tool alongside us.

Two principles shape every decision below:

1. **Provenance-first.** Every bundle leads with what we *discovered that was never
   declared*. That is the one page a self-attestation tool structurally cannot produce.
2. **Candidate, not verdict.** Per project doctrine, findings are *candidate compliance
   signals requiring human and legal review — never enforcement determinations*. The
   bundles must present themselves that way. This is not a weakness; it is the
   professional posture a CIO's counsel will trust, and it is a differentiator.

---

## 2. What already exists (reuse, do not rebuild)

| Asset | State | Reuse plan |
|---|---|---|
| `GET /api/reports/generate?city=X` | One blended branded DOCX | Becomes one preset call into the new engine |
| `backend/scripts/generate_report.py` | Branded DOCX primitives: cover, headings, hyperlinks, borders, brand config | Extracted into the render layer; primitives kept |
| `stores/reports.js` + CityDetail "Compliance Report" button | Per-city download, no history | Kept as a shortcut; superseded by the Reports section |
| `compliance-report` skill | Describes the single blended doc | Rewritten for presets (delivered as installable `.skill`) |
| `safeharbor.py`, `remediation.py`, `inventory` data | Live section data | Fed into bundle sections |

**Net:** the content engine and branded DOCX primitives are real and good. What is
missing is audience tailoring, PDF, a Reports section, snapshots, and the
premium/defensibility layer.

---

## 3. The core idea: one engine, named presets

A bundle is **sections + optional attachments**. A "single document" and an "auditor
package" differ only by *which sections*, *how deep*, and *whether supporting files ride
along*. So we build ONE engine and expose a small set of **presets**.

```
bundle_spec(city_data, audience, depth) -> BundleModel
    audience  -> which sections + tone
    depth     -> summary | full ; whether attachments are included
```

### Preset matrix (v1 ships the two poles; the rest are config)

| Preset | Audience | Depth | Output | Attachments |
|---|---|---|---|---|
| **Council Brief** | Elected officials | summary | single PDF (+DOCX) | none |
| **AG / Auditor Package** | Enforcement / external auditor | full | zip: PDF + attachments | inventory export, provenance appendix, audit-log excerpt, methodology |
| Procurement Inventory *(fast-follow)* | Procurement officer | medium | single PDF (+DOCX) | inventory export |
| CIO / Technical *(fast-follow)* | Internal IT | full | single PDF (+DOCX) | inventory export, provenance appendix |

**Presets are declared as data, not code** (governance-as-code): an audience→sections
map lives in `SCHEMA_DEFINITION.json` (`Report_Bundles` block), so adding an audience is
a config change, not a rewrite — consistent with the single-swap-point rule.

### Section catalogue (each is a pure builder)

- Cover + document control (ID, UTC timestamp, tool version, content hash, classification)
- **Discovered-vs-declared summary (provenance-first — always page one after cover)**
- Executive status (plain language; the whole of the Council Brief)
- AI asset inventory (by provenance: website / OAuth / procurement / agenda / declared)
- Compliance status detail (TRAIGA status, cure clock)
- Violations & cure period (citations anchored to Tex. Bus. & Com. Code Ch. 552)
- Remediation recommendations
- Statutory reference
- **Methodology & limitations** (how discovery works; candidate-vs-confirmed; out-of-line
  observer statement) — auditor package only
- **Human attestation block** (named reviewer sign-off) — full-depth presets

---

## 4. What makes it "high value" (defensibility layer)

These are cheap to add and disproportionately credible:

1. **Tamper-evidence.** Every bundle carries a document ID, UTC generation time, the tool
   release (from VERSION), and a **SHA-256 of its own content**. An auditor can verify it
   was not altered. The hash is printed in the document control block and stored on the
   snapshot record.
2. **Human attestation block.** A named-reviewer sign-off closes every full-depth bundle,
   because findings are candidate signals, not determinations. Honest and premium.
3. **Methodology appendix.** Turns the discovery engine into a documented strength on
   paper: how assets were found, what confidence means, the observer disclaimer.
4. **Provenance-first ordering.** Discovered-vs-declared is page one of substance.

---

## 5. Architecture (obeys the two-layer rules)

```
FRONTEND  ReportsView / GenerateDialog
            -> stores/reports.js
              -> ReportsService.js
                -> FastAPI /api/reports/*
BACKEND   api/routes/reports.py            (thin: RBAC, tenancy, call orchestrator)
            -> core/reporting/bundle_orchestrator.py   (pull repo data, render, persist)
                -> engine/reporting/bundle_spec.py     (PURE: data+preset -> BundleModel)
                -> engine/reporting/render_docx.py     (BundleModel -> DOCX; reuses primitives)
                -> engine/reporting/render_pdf.py      (BundleModel -> PDF)
                -> core/reporting/artifact_store.py    (ABSTRACTION, single swap point)
                     ├── LocalArtifactStore   (beta)
                     └── GcsArtifactStore      (production)
                -> repo.save_report_snapshot(...)      (metadata + hash + version)
```

Key rules honored:

- **`engine/reporting/` is pure and storage-agnostic.** `bundle_spec` takes dicts and
  returns a `BundleModel`; renderers take a `BundleModel` and return bytes. No repo, no
  HTTP, no network. Fully unit-testable with a `MockRepository`.
- **Artifact bytes go through an `ArtifactStore` Protocol** — the same
  interface-first / single-swap-point pattern as `GovernanceRepository`. Beta writes to
  local disk / the repo; production writes to Cloud Storage. Swapping is one line in
  `main.py`.
- **Snapshot metadata rides the existing repository Protocol.** New methods
  `save_report_snapshot`, `get_report_snapshots(city)`, `get_report_snapshot(id)` added to
  the Protocol and implemented in Sheets, Firestore, and Mock repos.
- **Frontend never renders documents itself.** It shows a live **HTML preview** (fast,
  on-brand) and downloads the artifact. No embedded DOCX/PDF viewer.
- **Governance-first security placeholders** on every new function (RBAC + tenancy TODOs)
  exactly as the existing routes carry them.

---

## 6. Output formats

- **PDF is the hero** — locked, portable, what goes to AG / council / auditor.
- **DOCX** kept as the editable internal companion.
- **Zip** for the auditor package (PDF + attachments).
- PDF rendering: reuse the branded design system already in `generate_report.py`; render
  via a library available in the backend image (reportlab is already a dependency and is
  used elsewhere). No headless-Chrome dependency in the request path.

---

## 7. Persistence — the Evidence Room

- Each generated bundle is stored as an **immutable snapshot**: artifact bytes in the
  `ArtifactStore`, plus a metadata record `{id, city, preset, audience, generated_utc,
  tool_release, sha256, size, generated_by, source_data_fingerprint}`.
- **Stale detection.** The snapshot records a fingerprint of the source data (scorecard +
  inventory + violations) at generation time. If the live fingerprint later differs, the
  snapshot is flagged **stale** in the UI — "the data changed since this was generated."
- **Retention (open decision — see §11).** Default proposal: keep all snapshots; no
  auto-delete (evidence should not silently vanish). Deletion is a deliberate admin act
  and audit-logged. Never a hard delete from the UI in beta.
- **Tenancy & RBAC.** Snapshots are scoped to the city; an agency user sees only their
  cities. Generation and download are admin/reviewer actions, audit-logged.

---

## 8. Reports / Evidence Room — UI & IA (executive-grade)

New left-nav item: **"Reports"** (working name; "Evidence Room" is the premium alt —
naming decision deferred).

- **Reports home.** A clean table/grid of snapshots: city, preset, audience, date,
  version, status chip (Current / Stale). Prominent primary action: **New evidence
  bundle**. Empty state that explains the feature.
- **Generate flow (dialog or wizard).** Pick city → pick preset (cards: Council Brief /
  AG-Auditor Package / …) → **live HTML preview rendered on-brand** → Generate. A spinner
  with honest progress, then the artifact + a saved snapshot.
- **Bundle detail.** Metadata, what's included, the provenance highlight
  (discovered-vs-declared counts), the content hash, download buttons (PDF / DOCX / zip),
  Regenerate, and a Stale banner when applicable.
- **Design language.** Consistent with the existing Vuetify theme; generous spacing,
  status color system already in the app, card-based, responsive per the mobile work
  already shipped. The preview is the "wow" — it must look like something a CIO would put
  in front of council.

---

## 9. Data model / schema additions

- `SCHEMA_DEFINITION.json` → new `Report_Bundles` block: preset definitions
  (audience, depth, ordered section keys, attachment keys, output formats). Adding an
  audience = editing this block.
- Repository Protocol → `save_report_snapshot`, `get_report_snapshots`,
  `get_report_snapshot`.
- Types (frontend `types.js`) → `ReportPreset`, `ReportSnapshot`, `BundlePreviewModel`.

---

## 10. Testing strategy

- **Pure `bundle_spec` tests** (sandbox-runnable, no I/O): each preset yields the right
  ordered sections; Council Brief excludes methodology/attachments; auditor package
  includes them; provenance-first ordering holds; candidate assets never render as
  determinations.
- **Renderer tests:** DOCX and PDF build without error from a fixture `BundleModel`; the
  content hash is deterministic for identical input and changes when content changes.
- **Snapshot tests:** save/get round-trips via `MockRepository`; stale detection flips
  when the source fingerprint changes; identities/secrets never enter a snapshot.
- **ArtifactStore tests:** Local and (mocked) GCS satisfy the same Protocol.
- **RBAC/tenancy tests:** a viewer cannot generate; an agency user cannot see another
  city's snapshots.
- **Verification step:** a subagent review of the auditor package against the
  candidate-not-verdict doctrine before ship.

---

## 11. Open decisions / risks

1. **Snapshot retention & storage location.** Proposed: keep-all, GCS in prod, local in
   beta, admin-only audit-logged deletion. Confirm before Phase 2.
2. **Naming:** "Reports" vs "Evidence Room."
3. **PDF fidelity:** reportlab reuse vs a richer renderer. Start with reportlab (in-image,
   no new infra); revisit only if design fidelity demands it.
4. **Attestation workflow depth:** a printed sign-off block now; a real in-app
   reviewer-approval workflow is a later phase, not v1.

---

## 12. Phasing

- **Phase 1 — Bundle engine + two presets.** `bundle_spec`, DOCX+PDF renderers,
  tamper-evidence, attestation, methodology, provenance-first. Council Brief +
  AG/Auditor Package. On-demand (no persistence yet) so the documents can be reviewed.
- **Phase 2 — Evidence Room + persistence.** `ArtifactStore` abstraction, snapshot
  Protocol methods, stale detection, the Reports section, history, live HTML preview.
- **Phase 3 — Fast-follow audiences** (Procurement, CIO Technical) — config only.
- **Phase 4 — Documentation (below), as the closing step of the feature.**

---

## 13. Documentation — the closing phase (and a new skill)

**Tooling gap found:** `update-user-guide` covers only the END-USER manual
(USER_GUIDE.md + .docx + PDF). It does NOT cover the broader product docs (FEATURES,
ARCHITECTURE, OPERATIONS, ROADMAP, PROJECT_BRAIN, INVENTORY_SPEC, DOC_STATUS, design
docs). Those have been updated by hand every release. So Phase 4 has two parts:

**13a. Create a `product-docs` skill** (delivered as an installable `.skill`). It keeps
the product/architecture docs in sync the same disciplined way `update-user-guide` keeps
the manual: given a shipped change, it drafts updates to FEATURES, ARCHITECTURE,
OPERATIONS, ROADMAP, PROJECT_BRAIN, INVENTORY_SPEC and flips DOC_STATUS rows —
drafting for human review, never auto-publishing. This closes the manual-doc gap for
every future feature, not just this one.

**13b. Apply it to Evidence Bundles.** Update, and explain the *benefit* in each:

- **USER_GUIDE.md** (via `update-user-guide`) — a "Reports / Evidence Room" section: how
  to generate a Council Brief and an AG/Auditor Package, what each contains, what the
  stale flag and content hash mean, and *why it matters* (defensible, reproducible
  evidence you can hand to council or an auditor).
- **FEATURES.md** — the capability, with the benefit framed for a buyer (own your
  compliance evidence; provenance-first; tamper-evident).
- **ARCHITECTURE.md** — the engine/orchestrator/ArtifactStore layering and the
  single-swap-point for storage.
- **OPERATIONS.md** — snapshot storage, retention, and the GCS wiring (via `cloud-setup`).
- **ROADMAP.md** — mark Phase 1–3 shipped as they land; note fast-follow audiences.
- **INVENTORY_SPEC.md** — how provenance flows into the discovered-vs-declared section.
- **DOC_STATUS.md** — this design doc PARTIAL→SHIPPED as phases land.
- **PROJECT_BRAIN.md** — the bundle-engine mental model and the candidate-not-verdict rule
  as it applies to outputs.

Every doc edit states the **benefit**, not just the change — so the docs double as sales
and onboarding material.

---

## 14. Next Steps for Scale

- Snapshots make the app a data controller for compliance evidence — SOC 2 posture and a
  written retention policy become real requirements before broad rollout (already flagged
  as a procurement gate elsewhere).
- The preset config is the seam for *other states*: a Colorado or federal bundle is a new
  `Report_Bundles` entry once that framework is crosswalked — same engine, new preset.
- The attestation block is the entry point for a future reviewer-approval workflow and,
  eventually, e-signature.
