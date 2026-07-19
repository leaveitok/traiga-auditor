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
