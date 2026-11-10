export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'
export const THEME_STORAGE_KEY = 'sudothink-theme'

function normalizePreference(value: string | null): ThemePreference {
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function createThemeController(target: Window, onChange?: (preference: ThemePreference, theme: ResolvedTheme) => void) {
  const media = target.matchMedia('(prefers-color-scheme: dark)')
  let preference: ThemePreference = 'system'
  let resolvedTheme: ResolvedTheme = 'light'
  try {
    preference = normalizePreference(target.localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    // 浏览器禁用存储时仍可跟随系统，并在当前页面切换。
  }

  function apply() {
    resolvedTheme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference
    const root = target.document.documentElement
    root.classList.toggle('dark', resolvedTheme === 'dark')
    root.style.colorScheme = resolvedTheme
    onChange?.(preference, resolvedTheme)
  }

  function onSystemChange() {
    if (preference === 'system') apply()
  }

  function onStorage(event: StorageEvent) {
    if (event.key !== THEME_STORAGE_KEY && event.key !== null) return
    preference = normalizePreference(event.newValue)
    apply()
  }

  media.addEventListener('change', onSystemChange)
  target.addEventListener('storage', onStorage)
  apply()

  return {
    get preference() { return preference },
    get resolvedTheme() { return resolvedTheme },
    setPreference(value: ThemePreference) {
      preference = normalizePreference(value)
      try {
        target.localStorage.setItem(THEME_STORAGE_KEY, preference)
      } catch {
        // 保留当前页面的选择，不因存储失败中断应用。
      }
      apply()
    },
    dispose() {
      media.removeEventListener('change', onSystemChange)
      target.removeEventListener('storage', onStorage)
    },
  }
}
