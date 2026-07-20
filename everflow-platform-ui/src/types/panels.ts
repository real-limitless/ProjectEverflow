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

export type ChatRole = 'user' | 'assistant' | 'system'
export type ChatMode = 'ask' | 'edit' | 'auto'
export type AgentRole = 'frontend' | 'backend' | 'planner' | 'architect' | 'general'

export interface ChatAgentRef {
  id: string
  name: string
  role: AgentRole
}

export interface ChatAttachment {
  id: string
  name: string
  mime: string
  sizeLabel: string
  kind: 'file' | 'image'
  previewUrl?: string
}

export interface WebSearchResult {
  title: string
  url: string
  snippet: string
}

export interface ChatBlock {
  type:
    | 'text'
    | 'markdown'
    | 'image'
    | 'attachment'
    | 'terminal'
    | 'web_search'
    | 'tool'
    | 'question'
  text?: string
  language?: string
  imageUrl?: string
  alt?: string
  attachment?: ChatAttachment
  terminal?: { command: string; output: string; exitCode?: number }
  webSearch?: { query: string; results: WebSearchResult[] }
  tool?: { title: string; body: string; status?: 'done' | 'running' | 'error' }
  options?: string[]
}

export interface ChatMessageMetrics {
  ttftMs?: number
  tokensPerSec?: number
  completionTokens?: number
}

export interface ChatMessage {
  id: string
  role: ChatRole
  agent?: ChatAgentRef
  thinking?: string
  blocks?: ChatBlock[]
  /** Plain text fallback / user edit source */
  text?: string
  /** Legacy single tool card */
  tool?: { title: string; body: string }
  metrics?: ChatMessageMetrics
  createdAt?: string
}

export interface ConversationMetrics {
  contextUsedTokens: number
  contextWindowTokens: number
  tokensPerSec: number
  ttftMs: number
}

export interface ChatConversation {
  id: string
  title: string
  meta: string
  pinned: boolean
  agents: ChatAgentRef[]
  messages: ChatMessage[]
  metrics: ConversationMetrics
  chatMode: ChatMode
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
  /** Active agents participating in this chat instance */
  enabledAgents?: string[]
  chatMode?: ChatMode
  /** Preview multi-service */
  previewServiceId?: string
  previewUrl?: string
}

export interface PanelMeta {
  label: string
  icon: string
}
