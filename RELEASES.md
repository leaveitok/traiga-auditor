# Release Log — TRAIGA Auditor

**This file is written by machines, not by hand.** Every `ship_*.bat` calls
`_release_stamp.bat`, which bumps `VERSION`, appends one row below, and commits both
alongside the change. That is the whole point: the record is a *byproduct of shipping*,
so it cannot drift from what actually shipped. If you find yourself editing this table
manually, something in the pipeline is broken — fix that instead.

## How to read it

- **Release** — the number shown on the dashboard under **Settings → Version & Build**.
  Ask a pilot city for this number and you can find the exact change here.
- **Bat** — the script that shipped it. Open it; its header comments explain the change
  in far more detail than one table row can.
- Rows are **append-only and chronological** (oldest first), like the audit log. Nothing
  is ever rewritten.

## Numbering

`MAJOR.MINOR`, e.g. `01.7`.

- **MINOR** increments on every ship. It carries no meaning beyond "later than".
- **MAJOR** is bumped by hand, deliberately, at a milestone worth naming. `01` is the
  pre-GA beta line. `02` is reserved for the first release a pilot city runs in
  production — see the note below.

## Important caveat

This table records what was **pushed**, not what is **running**. If CI goes red after a
green push, this file will say `01.8` while Cloud Run still serves `01.7`. The
authoritative answer to "what is live?" is always the **Settings → Version & Build**
panel, which reads the deployed backend directly. Trust the panel over this file.

## History

Releases before `01.0` were shipped without stamping and are not reconstructable —
mapping past commits back to the bat that shipped them would be guesswork, and a
version table you cannot trust is worse than none. `01.0` is therefore a baseline
meaning "the state of production at the moment stamping was introduced," not "the
first release." Use `git log` for anything earlier.

| Release | Date (UTC) | Bat | Change |
|---------|------------|-----|--------|
| 01.1 | 2026-07-19 | ship_release_versioning.bat | Introduce release stamping: VERSION, RELEASES.md, /health release, Settings display |
| 01.2 | 2026-07-19 | ship_oauth_partner_harvest.bat | OAuth signature harvest; recover tenant-wide + signInAudience; fix qualified-name matching via publisher |
| 01.3 | 2026-07-19 | ship_oauth_script_delivery.bat | Serve the export script from the app with a computed checksum; fix the commit guard |
| 01.4 | 2026-07-19 | ship_oauth_two_methods.bat | Browser-only Graph Explorer path; Unblock-File fix; in-UI step-by-step instructions |
| 01.5 | 2026-07-25 | ship_evidence_bundles.bat | Evidence Bundles Phase 1: audience presets, PDF+DOCX, package, tamper hash, Reports section |
| 01.6 | 2026-07-25 | ship_evidence_room.bat | Evidence Bundles Phase 2: Evidence Room - immutable snapshots, stale detection, tombstone; auth-safe downloads |
| 01.7 | 2026-07-25 | ship_deploy_fix.bat | Fix backend deploy red since 01.1: quote APP_RELEASE in env.yaml (YAML float coercion); surface Reports preset-load error |
| 01.8 | 2026-07-25 | ship_deploy_fix.bat | Fix backend deploy red since 01.1: quote APP_RELEASE in env.yaml (YAML float coercion); surface Reports preset-load error |
| 01.9 | 2026-07-25 | ship_deploy_fix.bat | Fix backend deploy red since 01.1: quote APP_RELEASE in env.yaml (YAML float coercion); surface Reports preset-load error |
| 01.10 | 2026-07-25 | ship_hardening_and_citation.bat | Quote all env.yaml values + validate step (deploy hardening); name TRAIGA/HB 149 on findings |
| 01.11 | 2026-07-25 | ship_sb1964_lens.bat | SB 1964 government AI code-of-ethics lens: 14-control crosswalk, setting, framework-parameterized Alignment Statement (no engine change) |
| 01.12 | 2026-08-21 | ship_oauth_google_docs.bat | Docs: Google Workspace OAuth channel - user guide v1.6 (md/docx/in-app PDF), DISCOVERY_EXPANSION_DESIGN acquisition, INVENTORY_SPEC discovered_oauth |
| 01.13 | 2026-08-23 | ship_ov_retheme.bat | UI-1: OpticVector retheme - OV palette both themes, flat hairline cards, Montserrat structural type, OV favicon, docs/DESIGN_SYSTEM.md |
| 01.14 | 2026-08-23 | ship_ov_lockup.bat | UI-2: OV monogram + OpticVector-TRAIGA Auditor lockup with GOVERN chip in the nav drawer |
| 01.15 | 2026-08-23 | ship_inventory_badges.bat | UI-3a: uniform Source-column badge stack in AI Inventory; PROJECT_BRAIN lessons 11-12 (bat-template provenance, fastapi 422 drift) |
| 01.16 | 2026-08-23 | ship_crisp_toolbars_tiles.bat | UI-3b: Add Data menu consolidation, flat stat tiles everywhere, outlined city-detail actions, humanized verification labels, user guide v1.7 |
| 01.17 | 2026-08-23 | ship_crisp_stealth_states.bat | UI-3c: stealth tonal-contrast fix, neutral city-detail header (score carries band color), skeleton loading rows + KPI skeleton tiles |
| 01.18 | 2026-08-23 | ship_pin_webstack.bat | PIN-1: pin fastapi/starlette/pydantic/slowapi as a set - local can no longer drift from the CI-proven window (2026-08-23 422 incident) |
| 01.19 | 2026-08-23 | ship_ui_delight.bat | UI-6: delight pass - 150ms route motion, count-up stat numerals, DESIGN_SYSTEM v1.1 Motion and data-viz honesty - sparklines deferred to the KPI history store |
| 01.20 | 2026-08-24 | ship_ui_navy_chrome.bat | UI-7: navy chrome in both themes - drawer and mobile app bar stay navy in Light, matching the CivicRoute rail; DESIGN_SYSTEM rule 1 extended with the NN/g grounding |
