import type { LayoutNode } from '@/types/dock'
import type { PanelInstanceState, PanelKey } from '@/types/panels'
import type { PaletteMode, Project } from '@/types/project'

export const LAYOUT_STORE_KEY = 'everflow-ui-layouts-v1'

export interface PersistedPlayground {
  openProjectIds: string[]
  /** null when no project is open */
  currentProjectId: string | null
  groupIdSeq: number
  instanceSeq: number
  instanceState: Record<string, PanelInstanceState>
  projectLayouts: Record<string, LayoutNode>
  paletteMode?: PaletteMode
  palettePos?: { x: number; y: number }
  /** User-created demo projects (not in seed catalog) */
  userProjects?: Record<string, Project>
}

export function loadPersisted(): PersistedPlayground | null {
  try {
    const raw = localStorage.getItem(LAYOUT_STORE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as PersistedPlayground
    if (!data?.projectLayouts) return null
    return data
  } catch {
    return null
  }
}

export function savePersisted(data: PersistedPlayground): void {
  try {
    localStorage.setItem(LAYOUT_STORE_KEY, JSON.stringify(data))
  } catch {
    /* ignore quota */
  }
}

export function emptyGroup(id: string): LayoutNode {
  return { type: 'group', id, tabs: [] as PanelKey[], active: null }
}
