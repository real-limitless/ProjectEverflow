import { PANEL_META } from '@/data/panelMeta'
import type { PanelKey, PanelType } from '@/types/panels'
import { PANEL_TYPES } from '@/types/panels'

export function typeOf(key: PanelKey | string): PanelType | '' {
  if (!key) return ''
  if ((PANEL_TYPES as readonly string[]).includes(key)) return key as PanelType
  const i = String(key).indexOf(':')
  const t = i >= 0 ? key.slice(0, i) : key
  return (PANEL_TYPES as readonly string[]).includes(t) ? (t as PanelType) : ''
}

export function panelMetaOf(key: PanelKey | string) {
  const t = typeOf(key)
  return t ? PANEL_META[t] : null
}

export function isPanelType(value: string): value is PanelType {
  return (PANEL_TYPES as readonly string[]).includes(value)
}
