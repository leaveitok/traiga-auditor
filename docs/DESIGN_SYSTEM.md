# OpticVector Design System — v1 (unified)

**Status:** ADOPTED for TRAIGA Auditor as of release UI-1 (see RELEASES.md).
**Origin:** the GovAssist console theme (`govassist/frontend/src/plugins/vuetify.js`,
GovAssist release 00.22) is the reference implementation. This file is the TRAIGA
repo's stamped copy of the shared tokens — the two repos deliberately share **no
runtime dependency** (CLAUDE.md rule), so the design system travels as a versioned
document + hand-synced `vuetify.js` values, governance-as-code style.
**Approved direction:** the "OpticVector Platform UI" design canvas (2026-08-23).

## Core tokens

| Token | Hex | Role |
|---|---|---|
| Navy | `#0F1E2D` | Chrome: app bars, nav drawers, dark surfaces. Carries the brand. |
| OV Blue | `#3E9BE0` | `primary` — the ONLY interactive color in every module (buttons, links, focus). |
| OV Blue darken-1 | `#2F83C4` | Hover/pressed on primary. |
| Auditor Teal | `#1F9C8C` | TRAIGA Auditor module accent (`accent`). Lockups and module badges only — never buttons. |
| CivicRoute Amber | `#F2A900` | CivicRoute 311 module accent (in the GovAssist repo). |
| Success | `#1A7F5A` | Semantic: compliant / on-track. |
| Warning | `#B45309` | Semantic: in-cure / at-risk. |
| Error | `#C0392B` | Semantic: non-compliant / breached. |
| Background | `#F6F8FA` | App background. |
| Surface | `#FFFFFF` | Cards, panels. |

Stealth (dark) theme re-expresses the same tokens on the navy family:
primary `#66B5EC`, accent `#3FC1AD`, success `#43C08A`, warning `#F2B33D`,
error `#E57368`, background `#0B1620`, surface `#12202E`.

## Rules

1. **One navy chrome, one accent per module.** Product identity is expressed by the
   accent chip in the lockup (Auditor teal · GOVERN, GovAssist blue · ANSWER,
   CivicRoute amber · ROUTE) — never by changing the palette per product.
2. **OV Blue is the only interactive color.** Accents and status colors are never
   used for buttons or links.
3. **Status colors are semantic and identical across modules.** Compliant green,
   in-cure amber, non-compliant red mean the same thing on every screen; a status
   color is never a product accent.
4. **Flat cards, hairline borders.** `VCard: { elevation: 0, border: true }` — no
   Material elevation on content surfaces. Navy chrome carries the depth.
5. **Montserrat marks structure** (page titles, card titles, lockups, weights
   500/600/700); Roboto stays for body and data — density and familiarity win in
   tables. Loaded via Google Fonts in `index.html`.
6. **Global defaults over per-view edits.** All of the above lands in
   `src/plugins/vuetify.js` defaults/tokens or one `App.vue` style block; view
   files are not edited for theme (frontend-change skill rule).

## Sync procedure

When a token changes: update this file FIRST, then apply to both repos'
`vuetify.js` in the same working session, each through its own ship bat. If the
values in either repo disagree with this file, this file wins — fix the repo.

## Deliberately out of scope (v1)

Typography scale changes, component redesigns, spacing system, dark-mode for the
GovAssist console. Candidates for later slices; see the UI slice plan.
