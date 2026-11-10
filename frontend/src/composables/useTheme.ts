import { readonly, ref } from 'vue'
import { createThemeController, type ResolvedTheme, type ThemePreference } from '@/utils/theme'

const preference = ref<ThemePreference>('system')
const resolvedTheme = ref<ResolvedTheme>('light')
let controller: ReturnType<typeof createThemeController> | undefined

export function initializeTheme() {
  controller ??= createThemeController(window, (mode, theme) => {
    preference.value = mode
    resolvedTheme.value = theme
  })
  return controller
}

export function useTheme() {
  const theme = initializeTheme()
  return {
    preference: readonly(preference),
    resolvedTheme: readonly(resolvedTheme),
    setPreference: theme.setPreference,
  }
}
