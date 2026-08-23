import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

// Components and directives are auto-imported by vite-plugin-vuetify
export default createVuetify({
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  // Where "mobile" begins. Vuetify's DEFAULT is 'lg' (1280px), which would flip a
  // 1366x768 laptop, a split-screen window, or a smaller monitor into the mobile
  // overlay layout — changing the desktop design we already have. Pin it to 'md'
  // (960px) so: >=960px keeps the existing permanent-drawer desktop UI unchanged,
  // and only phones / portrait tablets get the overlay drawer + app bar.
  display: {
    mobileBreakpoint: 'md',
  },
  theme: {
    // NOTE: themes are keyed by name. To add a new theme later, add a palette
    // here and a matching entry in src/composables/useAppTheme.js — no other
    // code changes needed (nav toggle + Settings render from that list).
    defaultTheme: 'light',
    themes: {
      // OpticVector Design System v1 (shared with the GovAssist console).
      // primary = OV Blue, the ONLY interactive color; navy is chrome;
      // 'accent' is this module's product accent (Auditor teal) - used for
      // the brand lockup and module badges, never for buttons.
      // Status colors stay SEMANTIC (compliant green / in-cure amber /
      // non-compliant red) and match the GovAssist palette exactly, so the
      // two products read as siblings side by side in a demo.
      light: {
        colors: {
          primary:    '#3E9BE0',   // OpticVector blue - buttons, links, focus
          'primary-darken-1': '#2F83C4',
          secondary:  '#0F1E2D',   // OpticVector navy - chrome
          navy:       '#0F1E2D',   // custom: app bar / dark surfaces
          accent:     '#1F9C8C',   // TRAIGA Auditor module accent (teal)
          success:    '#1A7F5A',   // Compliant green
          warning:    '#B45309',   // In-cure amber
          error:      '#C0392B',   // Non-compliant / expired red
          info:       '#3E9BE0',
          background: '#F6F8FA',
          surface:    '#FFFFFF',
        },
      },
      // Stealth: dark, low-glare palette for technical users. Status colors are
      // brightened so compliant/in-cure/non-compliant stay legible on dark.
      stealth: {
        dark: true,
        colors: {
          primary:    '#66B5EC',   // OV blue brightened for dark surfaces
          secondary:  '#93AABF',
          navy:       '#0F1E2D',
          accent:     '#3FC1AD',   // Auditor teal brightened for dark
          success:    '#43C08A',
          warning:    '#F2B33D',
          error:      '#E57368',
          info:       '#66B5EC',
          background: '#0B1620',    // navy-black (navy family, was neutral slate)
          surface:    '#12202E',    // cards / panels
        },
      },
    },
  },
  defaults: {
    // Flat cards with a hairline border instead of Material elevation - the
    // single highest-leverage "modern" move; every card in the app inherits.
    VCard:   { elevation: 0, rounded: 'lg', border: true },
    VBtn:    { variant: 'flat' },
    VChip:   { size: 'small' },
    // Responsive tables, set once for every table in the app. Below the `sm`
    // breakpoint Vuetify stacks each row into a labelled card instead of a wide
    // grid, which is what makes the data views usable on a phone. Adding a new
    // table anywhere inherits this automatically — no per-view work.
    VDataTable:        { mobileBreakpoint: 'sm' },
    VDataTableServer:  { mobileBreakpoint: 'sm' },
    VDataTableVirtual: { mobileBreakpoint: 'sm' },
  },
})
