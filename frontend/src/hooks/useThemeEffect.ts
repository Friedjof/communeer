import { useEffect } from 'react'
import { applyTheme, useUiStore } from '@/lib/uiStore'

/** Applies the persisted theme to <html> on mount/change, and reacts to OS theme changes when in "system" mode. */
export function useThemeEffect() {
  const theme = useUiStore((state) => state.theme)

  useEffect(() => {
    applyTheme(theme)

    if (theme !== 'system') return

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const listener = () => applyTheme('system')
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [theme])
}
