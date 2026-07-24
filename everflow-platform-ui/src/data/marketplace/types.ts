export type MarketplaceKind = 'skill' | 'command' | 'plugin' | 'tool' | 'mcp'

export type MarketplaceTab = 'skills' | 'commands' | 'plugins' | 'tools' | 'mcp'

export interface MarketplaceItem {
  id: string
  kind: MarketplaceKind
  name: string
  description: string
  origin: string
  source: string
  tags?: string[]
  contentUrl?: string
  mcpConfig?: Record<string, unknown>
  httpTool?: {
    name: string
    method: string
    url_template: string
    enabled?: boolean
  }
  contentFile?: string
  install?: {
    plugin?: string[]
    mcp?: Record<string, Record<string, unknown>>
    skills?: Array<{ id: string; contentUrl?: string; contentFile?: string; content?: string }>
  }
}

export interface MarketplaceCatalog {
  version: number
  source?: Record<string, string>
  counts?: Record<string, number>
  skills: MarketplaceItem[]
  commands: MarketplaceItem[]
  plugins: MarketplaceItem[]
  tools: MarketplaceItem[]
  mcps: MarketplaceItem[]
}

export interface MarketplaceInstalledItem {
  kind: string
  id: string
  source?: string
  name?: string
  installed_at?: string
  http_tool_id?: string
}

export interface MarketplaceInstalledResponse {
  project_id: string
  sandbox_status: string | null
  items: MarketplaceInstalledItem[]
  plugins: string[]
  manifest: Record<string, unknown>
}

export const MARKETPLACE_TABS: { id: MarketplaceTab; kind: MarketplaceKind; label: string }[] = [
  { id: 'skills', kind: 'skill', label: 'Skills' },
  { id: 'commands', kind: 'command', label: 'Commands' },
  { id: 'plugins', kind: 'plugin', label: 'Plugins' },
  { id: 'tools', kind: 'tool', label: 'Tools' },
  { id: 'mcp', kind: 'mcp', label: 'MCP' },
]

export function tabToKind(tab: MarketplaceTab): MarketplaceKind {
  return MARKETPLACE_TABS.find((t) => t.id === tab)?.kind ?? 'skill'
}

export function itemsForTab(catalog: MarketplaceCatalog, tab: MarketplaceTab): MarketplaceItem[] {
  switch (tab) {
    case 'skills':
      return catalog.skills
    case 'commands':
      return catalog.commands
    case 'plugins':
      return catalog.plugins
    case 'tools':
      return catalog.tools
    case 'mcp':
      return catalog.mcps
    default:
      return []
  }
}
