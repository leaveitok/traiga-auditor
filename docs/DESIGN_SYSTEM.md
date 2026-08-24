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
   CivicRoute amber · ROUTE) — never by changing the palette per product. The chrome is navy in
   **both themes** (UI-7, 2026-08-23): the nav drawer and mobile app bar stay
   Navy `#0F1E2D` in Light and Stealth alike — a light theme lightens the
   *workspace*, never the chrome. Grounding: NN/g's contrast-polarity research
   (Piepenbrock 2013; Dobres 2017) favors light content surfaces for dense
   data reading; the navy frame carries the brand while tables stay light.
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

## Motion & data-viz honesty (v1.1 — added by the delight pass, TRAIGA UI-6 / GovAssist GA-UI-2)

7. **One speed: 150ms ease-out, opacity/transform only.** View swaps fade + rise
   4px (the `ov-view` transition in `App.vue`); card hover states ease at the
   same speed. Nothing bounces, nothing travels further than 4px, and
   `prefers-reduced-motion: reduce` disables all of it (WCAG 2.3.3).
8. **Stat numerals count up (500ms, ease-out cubic) — presentation only.**
   `OvCountUp.vue` animates the paint, never the value; non-numeric values
   render verbatim with no animation, and reduced-motion snaps straight to the
   final figure.
9. **No sparklines until there is real data to draw.** Neither backend stores
   historical snapshots, so a trend line would be fabricated — on a governance
   product that is disqualifying — and with today's tenant sizes even honest
   distribution mini-charts are 3–6 bars, too thin to inform. Decision
   2026-08-23: charts in stat tiles wait for the KPI history store (a backend
   snapshot-per-scan slice). When that ships, any chart must be real data and
   must carry a label saying what it shows.

`OvCountUp.vue` is a hand-synced twin in both repos
(`frontend/src/components/`), same no-runtime-dependency rule as `vuetify.js`.

## Sync procedure

When a token changes: update this file FIRST, then apply to both repos'
`vuetify.js` in the same working session, each through its own ship bat. If the
values in either repo disagree with this file, this file wins — fix the repo.

## Deliberately out of scope (v1)

Typography scale changes, component redesigns, spacing system, dark-mode for the
GovAssist console, and **sparklines of any kind** (blocked on the KPI history
store per rule 9). Candidates for later
slices; see the UI slice plan.
