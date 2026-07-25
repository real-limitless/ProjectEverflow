export const PANEL_TYPES = [
  'chat',
  'preview',
  'desktop',
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

export interface ChatPermissionRequest {
  id: string
  title: string
  detail?: string
  patterns?: string[]
  status?: 'pending' | 'resolved'
}

export interface ChatQuestionOption {
  label: string
  description?: string
}

/** One prompt inside an OpenCode question request (may be multi-question). */
export interface ChatQuestionItem {
  header?: string
  question: string
  options: ChatQuestionOption[]
  multiple?: boolean
  custom?: boolean
}

export interface ChatQuestionRequest {
  /** OpenCode question request id (POST /question/{id}/reply) */
  id: string
  items: ChatQuestionItem[]
  status?: 'pending' | 'answered' | 'rejected'
}

export interface KnowledgeCitation {
  canvasId: string
  canvasName: string
  chunkId?: string
  text: string
  score?: number
  sourceUrl?: string
  path?: string
}

export interface ChatBlock {
  type:
    | 'text'
    | 'markdown'
    | 'image'
    | 'attachment'
    | 'terminal'
    | 'web_search'
    | 'knowledge_citations'
    | 'tool'
    | 'question'
    | 'permission'
  text?: string
  language?: string
  imageUrl?: string
  alt?: string
  attachment?: ChatAttachment
  terminal?: { command: string; output: string; exitCode?: number }
  webSearch?: { query: string; results: WebSearchResult[] }
  knowledgeCitations?: {
    query?: string
    hits: KnowledgeCitation[]
  }
  tool?: {
    title: string
    body: string
    status?: 'done' | 'running' | 'error'
    /** OpenCode tool name (bash, edit, read, …) */
    name?: string
    /** OpenCode part / call id for streaming upserts */
    callId?: string
  }
  options?: string[]
  /** Full OpenCode question request (preferred over flat options) */
  questionRequest?: ChatQuestionRequest
  permission?: ChatPermissionRequest
  /** Stable id for streaming part upserts */
  partId?: string
}

export interface ChatMessageMetrics {
  ttftMs?: number
  tokensPerSec?: number
  completionTokens?: number
  /** Context tokens used after this turn (from provider when available) */
  contextUsedTokens?: number
  /** Wall time for this completion (ms), if known */
  durationMs?: number
  /** Raw OpenCode token breakdown (for usage ingest). */
  inputTokens?: number
  outputTokens?: number
  reasoningTokens?: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  provider?: string
  model?: string
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
  /**
   * OpenCode generation status for assistant turns.
   * incomplete = still streaming / empty parts; complete = finished or error.
   */
  generationStatus?: 'incomplete' | 'complete' | 'error'
  /** Provider/model error message when generation fails */
  errorText?: string
}

export interface ConversationMetrics {
  contextUsedTokens: number
  contextWindowTokens: number
  tokensPerSec: number
  ttftMs: number
}

/** Isolated git worktree bound to a conversation (opt-in). */
export interface ConversationWorktree {
  repoId: string
  parentPath: string
  path: string
  branch: string
  status: 'active' | 'applied' | 'discarded' | 'error'
  error?: string
}

export interface ChatConversation {
  id: string
  title: string
  meta: string
  pinned: boolean
  /**
   * Historical / display participants (message author chips).
   * Prompt routing uses `primaryAgent`, not this list.
   */
  agents: ChatAgentRef[]
  /**
   * OpenCode agent name for the next prompt (e.g. plan, build, custom).
   * Independent of chatMode permission policy.
   */
  primaryAgent?: string
  messages: ChatMessage[]
  metrics: ConversationMetrics
  chatMode: ChatMode
  /** demo = local showcase; opencode = sandbox OpenCode session */
  source?: 'demo' | 'opencode'
  /**
   * User opted this chat into an isolated git worktree.
   * Worktree is created lazily on first Edit/Auto prompt when true.
   */
  useWorktree?: boolean
  /** Active / resolved worktree metadata when isolation is (or was) used */
  worktree?: ConversationWorktree
}

export interface PanelInstanceState {
  type: PanelType
  title?: string
  convId?: string
  messages?: ChatMessage[]
  /** Active code file path (or legacy file name) */
  file?: string
  /** Open editor tabs (paths); active is `file` */
  openFiles?: string[]
  /** Editor font size in px */
  codeFontSize?: number
  /** Expanded folder paths in the file tree */
  expandedFolders?: string[]
  /** Chat: hide conversation list for focus mode */
  railCollapsed?: boolean
  model?: string
  enabledTools?: string[]
  enabledMcps?: string[]
  enabledSkills?: string[]
  /** @deprecated Prefer primaryAgent for OpenCode routing; multi-agent list is display-only */
  enabledAgents?: string[]
  /**
   * Primary OpenCode agent for this chat instance (plan, build, …).
   * Independent of chatMode permission policy.
   */
  primaryAgent?: string
  chatMode?: ChatMode
  /**
   * When true (Ask/Edit only): do not hard-deny tools; require in-chat
   * Allow once / Always / Deny for sensitive actions. Default false = strict.
   */
  softPermissions?: boolean
  /** Preview multi-service */
  previewServiceId?: string
  previewUrl?: string
}

export interface PanelMeta {
  label: string
  icon: string
}
