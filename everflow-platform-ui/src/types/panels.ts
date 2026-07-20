export const PANEL_TYPES = [
  'chat',
  'preview',
  'knowledge',
  'code',
  'repository',
  'terminal',
  'workflows',
  'database',
  'jobs',
  'agents',
  'tools',
  'env',
  'tests',
  'deploy',
] as const

export type PanelType = (typeof PANEL_TYPES)[number]

export type PanelKey = `${PanelType}:${number}` | string

export interface ChatMessage {
  role: 'user' | 'assistant'
  text?: string
  thinking?: string
  tool?: { title: string; body: string }
}

export interface PanelInstanceState {
  type: PanelType
  title?: string
  convId?: string
  messages?: ChatMessage[]
  file?: string
  /** Chat: hide conversation list for focus mode */
  railCollapsed?: boolean
  model?: string
  enabledTools?: string[]
  enabledMcps?: string[]
  enabledSkills?: string[]
  chatMode?: 'ask' | 'auto'
  /** Preview multi-service */
  previewServiceId?: string
  previewUrl?: string
}

export interface PanelMeta {
  label: string
  icon: string
}
