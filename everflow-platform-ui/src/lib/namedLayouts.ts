import type { LayoutNode } from '@/types/dock'
import type { PanelInstanceState } from '@/types/panels'

export const NAMED_LAYOUTS_KEY = 'everflow-ui-named-layouts-v1'
export const THEME_KEY = 'everflow-ui-theme-v1'

export type ThemeMode = 'light' | 'dark'

export interface NamedLayoutSnapshot {
  id: string
  name: string
  savedAt: string
  projectId: string
  layout: LayoutNode
  instanceState: Record<string, PanelInstanceState>
  groupIdSeq: number
  instanceSeq: number
}

export function listNamedLayouts(): NamedLayoutSnapshot[] {
  try {
    const raw = localStorage.getItem(NAMED_LAYOUTS_KEY)
    if (!raw) return []
    const data = JSON.parse(raw) as NamedLayoutSnapshot[]
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}

export function saveNamedLayout(snapshot: NamedLayoutSnapshot): void {
  const list = listNamedLayouts().filter((s) => s.id !== snapshot.id)
  list.unshift(snapshot)
  localStorage.setItem(NAMED_LAYOUTS_KEY, JSON.stringify(list.slice(0, 30)))
}

export function deleteNamedLayout(id: string): void {
  const list = listNamedLayouts().filter((s) => s.id !== id)
  localStorage.setItem(NAMED_LAYOUTS_KEY, JSON.stringify(list))
}

export function loadTheme(): ThemeMode {
  try {
    const t = localStorage.getItem(THEME_KEY)
    return t === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function saveTheme(theme: ThemeMode): void {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* ignore */
  }
}

export function applyThemeClass(theme: ThemeMode): void {
  document.documentElement.classList.toggle('pf-v6-theme-dark', theme === 'dark')
}
