import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

interface UiState {
  theme: Theme
  selectedCommunityId: string | null
  setTheme: (theme: Theme) => void
  setSelectedCommunityId: (id: string | null) => void
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: 'system',
      selectedCommunityId: null,
      setTheme: (theme) => set({ theme }),
      setSelectedCommunityId: (id) => set({ selectedCommunityId: id }),
    }),
    { name: 'communeer-ui' },
  ),
)

function resolveTheme(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

/** Applies the current theme to <html class="dark">; call once at app root. */
export function applyTheme(theme: Theme) {
  const resolved = resolveTheme(theme)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}
