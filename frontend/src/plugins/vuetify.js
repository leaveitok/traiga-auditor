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
  theme: {
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
    },
  },
  defaults: {
    VCard:   { elevation: 2, rounded: 'lg' },
    VBtn:    { variant: 'flat' },
    VChip:   { size: 'small' },
  },
})
