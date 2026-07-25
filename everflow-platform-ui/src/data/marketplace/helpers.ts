import type {
  MarketplaceCatalog,
  MarketplaceItem,
  MarketplaceKind,
  MarketplaceTab,
} from './types'
import { itemsForTab, tabToKind } from './types'

/** Curated “featured” ids shown in the App Store strip (order matters). */
export const FEATURED_SKILL_IDS = [
  'everflow-knowledge',
  'everflow-jobs',
  'everflow-browser',
  'api-design',
  'fix',
  'commit',
  'review-pr',
  'explain',
]

export const FEATURED_PLUGIN_IDS = ['graphify', 'oh-my-opencode', 'headroom']
export const FEATURED_MCP_IDS = ['playwright', 'everflow']

export function originLabel(origin: string): string {
  if (origin === 'ecc') return 'ECC'
  if (origin === 'curated') return 'Curated'
  if (origin === 'everflow') return 'Everflow'
  return origin
}

export function kindLabel(kind: MarketplaceKind): string {
  switch (kind) {
    case 'skill':
      return 'Skill'
    case 'command':
      return 'Command'
    case 'plugin':
      return 'Plugin'
    case 'tool':
      return 'Tool'
    case 'mcp':
      return 'MCP'
    default:
      return kind
  }
}

export function parseKindParam(raw: string | undefined): MarketplaceKind | null {
  if (!raw) return null
  const k = raw.toLowerCase()
  if (k === 'skill' || k === 'command' || k === 'plugin' || k === 'tool' || k === 'mcp') {
    return k
  }
  // URL plural forms
  if (k === 'skills') return 'skill'
  if (k === 'commands') return 'command'
  if (k === 'plugins') return 'plugin'
  if (k === 'tools') return 'tool'
  if (k === 'mcps') return 'mcp'
  return null
}

export function kindToTab(kind: MarketplaceKind): MarketplaceTab {
  switch (kind) {
    case 'skill':
      return 'skills'
    case 'command':
      return 'commands'
    case 'plugin':
      return 'plugins'
    case 'tool':
      return 'tools'
    case 'mcp':
      return 'mcp'
  }
}

export function detailPath(kind: MarketplaceKind, id: string): string {
  return `/marketplace/${kind}/${encodeURIComponent(id)}`
}

export function filterMarketplaceItems(
  items: MarketplaceItem[],
  opts: { query?: string; tag?: string; origin?: string },
): MarketplaceItem[] {
  const q = (opts.query || '').trim().toLowerCase()
  const tag = (opts.tag || '').trim().toLowerCase()
  const origin = (opts.origin || '').trim().toLowerCase()
  return items.filter((item) => {
    if (origin && String(item.origin || '').toLowerCase() !== origin) return false
    if (tag && !(item.tags || []).some((t) => t.toLowerCase() === tag)) return false
    if (!q) return true
    return (
      item.name.toLowerCase().includes(q) ||
      item.id.toLowerCase().includes(q) ||
      item.description.toLowerCase().includes(q) ||
      (item.tags || []).some((t) => t.toLowerCase().includes(q))
    )
  })
}

export function paginateItems<T>(
  items: T[],
  page: number,
  pageSize: number,
): { pageItems: T[]; total: number; page: number; pageSize: number; pageCount: number } {
  const total = items.length
  const size = Math.max(1, pageSize)
  const pageCount = Math.max(1, Math.ceil(total / size) || 1)
  const safePage = Math.min(Math.max(1, page), pageCount)
  const start = (safePage - 1) * size
  return {
    pageItems: items.slice(start, start + size),
    total,
    page: safePage,
    pageSize: size,
    pageCount,
  }
}

export function collectTags(items: MarketplaceItem[], limit = 12): string[] {
  const counts = new Map<string, number>()
  for (const item of items) {
    for (const t of item.tags || []) {
      const key = t.trim()
      if (!key) continue
      counts.set(key, (counts.get(key) || 0) + 1)
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([t]) => t)
}

export function collectOrigins(items: MarketplaceItem[]): string[] {
  const set = new Set<string>()
  for (const item of items) {
    if (item.origin) set.add(item.origin)
  }
  return [...set].sort()
}

export function featuredItems(
  catalog: MarketplaceCatalog,
  tab: MarketplaceTab,
  limit = 8,
): MarketplaceItem[] {
  const rows = itemsForTab(catalog, tab)
  const byId = new Map(rows.map((r) => [r.id, r]))
  const kind = tabToKind(tab)
  let prefer: string[] = []
  if (kind === 'skill') prefer = FEATURED_SKILL_IDS
  else if (kind === 'plugin') prefer = FEATURED_PLUGIN_IDS
  else if (kind === 'mcp') prefer = FEATURED_MCP_IDS
  else if (kind === 'command') prefer = FEATURED_SKILL_IDS // overlap names when present

  const out: MarketplaceItem[] = []
  const seen = new Set<string>()
  for (const id of prefer) {
    const hit = byId.get(id)
    if (hit && !seen.has(hit.id)) {
      out.push(hit)
      seen.add(hit.id)
    }
    if (out.length >= limit) return out
  }
  // Everflow-origin first, then rest
  const rest = [
    ...rows.filter((r) => r.origin === 'everflow' && !seen.has(r.id)),
    ...rows.filter((r) => r.origin !== 'everflow' && !seen.has(r.id)),
  ]
  for (const r of rest) {
    out.push(r)
    if (out.length >= limit) break
  }
  return out
}

export function findCatalogItem(
  catalog: MarketplaceCatalog,
  kind: MarketplaceKind,
  id: string,
): MarketplaceItem | undefined {
  const tab = kindToTab(kind)
  return itemsForTab(catalog, tab).find((i) => i.id === id)
}

/** Stable hue 0–359 and monogram from id/name. */
export function itemIconStyle(id: string, name?: string): { hue: number; monogram: string } {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  const hue = h % 360
  const src = (name || id).trim()
  const parts = src.split(/[\s\-_/]+/).filter(Boolean)
  const monogram =
    parts.length >= 2
      ? (parts[0][0] + parts[1][0]).toUpperCase()
      : src.slice(0, 2).toUpperCase()
  return { hue, monogram: monogram || '??' }
}

export function supportsTryChat(kind: MarketplaceKind): boolean {
  return kind === 'skill' || kind === 'command'
}

export function supportsContentPreview(kind: MarketplaceKind): boolean {
  return kind === 'skill' || kind === 'command'
}
