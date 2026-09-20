export type Theme = 'system' | 'light' | 'dark'
export const THEME_STORAGE_KEY = 'garmin-health-sync.ui.v1.theme'

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  try { window.localStorage.setItem(THEME_STORAGE_KEY, theme) } catch { /* UI preferences are optional. */ }
}
