/**
 * useAppTheme — single source of truth for the interface theme.
 *
 * Themes are Vuetify named themes (see src/plugins/vuetify.js). Adding another
 * theme later is a data-only change: add a palette in vuetify.js + an entry in
 * APP_THEMES here; the nav toggle and the Settings control render from this list.
 * The choice is persisted to localStorage (per-browser) and restored at startup.
 */
import { useTheme } from 'vuetify'

const STORAGE_KEY = 'traiga.theme'

export const APP_THEMES = [
  { value: 'light',   label: 'Light',   icon: 'mdi-white-balance-sunny' },
  { value: 'stealth', label: 'Stealth', icon: 'mdi-weather-night' },
]
const VALID = new Set(APP_THEMES.map((t) => t.value))

export function useAppTheme() {
  const theme = useTheme()
  const currentName = () => theme.global.name.value
  const isDark = () => !!theme.global.current.value.dark

  function setTheme(name) {
    const next = VALID.has(name) ? name : 'light'
    theme.global.name.value = next
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* private mode: ignore */ }
  }

  /** Apply the saved theme (call once at startup, before first paint). */
  function restore() {
    let saved = null
    try { saved = localStorage.getItem(STORAGE_KEY) } catch { /* private mode: ignore */ }
    if (saved && VALID.has(saved)) theme.global.name.value = saved
  }

  function toggle() {
    setTheme(currentName() === 'stealth' ? 'light' : 'stealth')
  }

  return { theme, currentName, isDark, setTheme, restore, toggle, APP_THEMES }
}
