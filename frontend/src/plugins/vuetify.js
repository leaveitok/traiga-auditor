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
      light: {
        colors: {
          primary:    '#1565C0',   // City-grade navy blue
          secondary:  '#37474F',
          success:    '#2E7D32',   // Compliant green
          warning:    '#F57F17',   // In-cure amber
          error:      '#B71C1C',   // Non-compliant / expired red
          info:       '#0277BD',
          background: '#F5F7FA',
          surface:    '#FFFFFF',
        },
      },
      // Stealth: dark, low-glare palette for technical users. Status colors are
      // brightened so compliant/in-cure/non-compliant stay legible on dark.
      stealth: {
        dark: true,
        colors: {
          primary:    '#4FA3F7',   // brighter navy for dark surfaces
          secondary:  '#90A4AE',
          success:    '#4CAF50',
          warning:    '#FFB300',
          error:      '#EF5350',
          info:       '#42A5F5',
          background: '#0E1116',    // near-black slate
          surface:    '#171B22',    // cards / panels
        },
      },
    },
  },
  defaults: {
    VCard:   { elevation: 2, rounded: 'lg' },
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
