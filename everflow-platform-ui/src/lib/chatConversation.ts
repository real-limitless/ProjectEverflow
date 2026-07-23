import {
  CHAT_AGENTS,
  DEFAULT_CHAT_AGENTS,
  DEFAULT_CHAT_MODE,
  DEFAULT_CONTEXT_WINDOW,
  DEFAULT_PRIMARY_AGENT,
  agentById,
} from '@/data/chatCatalog'
import { defaultMetrics, seedConversationsForProject } from '@/data/chatShowcase'
import { isSeedProjectId, PROJECTS } from '@/data/projects'
import { isDemoMode } from '@/lib/api'
import {
  deriveTitleFromMessages,
  estimateTokens,
  messageToRaw,
  newMessageId,
} from '@/lib/chatMarkdown'
import type {
  ChatConversation,
  ChatMessage,
  ChatMode,
  PanelInstanceState,
} from '@/types/panels'

export function cloneConversations(list: ChatConversation[]): ChatConversation[] {
  return JSON.parse(JSON.stringify(list)) as ChatConversation[]
}

export function seedProjectConversations(projectId: string): ChatConversation[] {
  const p = PROJECTS[projectId]
  if (!p) return []

  // Showcase / hardcoded sample threads only for offline demo seeds
  const allowShowcase = isDemoMode() && isSeedProjectId(projectId)
  if (!allowShowcase) {
    if (p.conversations?.length) return cloneConversations(p.conversations)
    const title = p.convs?.[0]?.title || 'New chat'
    return [emptyConversation(title)]
  }

  if (p.conversations?.length) return cloneConversations(p.conversations)
  return seedConversationsForProject(projectId, p.convs, p.messages || [])
}

export function sortConversations(list: ChatConversation[]): ChatConversation[] {
  return [...list].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return 0
  })
}

export function findConversation(
  list: ChatConversation[] | undefined,
  convId: string | undefined,
): ChatConversation | undefined {
  if (!list || !convId) return undefined
  return list.find((c) => c.id === convId)
}

export function syncPanelFromConversation(
  conv: ChatConversation | undefined,
): Partial<PanelInstanceState> {
  if (!conv) {
    return {
      convId: undefined,
      title: 'Chat',
      messages: [],
      chatMode: DEFAULT_CHAT_MODE,
      enabledAgents: DEFAULT_CHAT_AGENTS,
      primaryAgent: DEFAULT_PRIMARY_AGENT,
    }
  }
  return {
    convId: conv.id,
    title: conv.title,
    messages: cloneMessages(conv.messages),
    chatMode: conv.chatMode,
    enabledAgents: conv.agents.map((a) => a.id),
    primaryAgent: conv.primaryAgent || DEFAULT_PRIMARY_AGENT,
  }
}

export function cloneMessages(messages: ChatMessage[]): ChatMessage[] {
  return JSON.parse(JSON.stringify(messages)) as ChatMessage[]
}

export function recomputeContext(messages: ChatMessage[]): number {
  const raw = messages.map((m) => messageToRaw(m)).join('\n')
  return Math.min(DEFAULT_CONTEXT_WINDOW, estimateTokens(raw) + 800)
}

export function demoAssistantReply(opts: {
  userText: string
  model: string
  mode: ChatMode
  tools: string[]
  /** Primary agent name for this turn */
  primaryAgent?: string
  retry?: boolean
}): ChatMessage[] {
  const {
    userText,
    model,
    mode,
    tools,
    primaryAgent = DEFAULT_PRIMARY_AGENT,
    retry = false,
  } = opts
  const ttftMs = 120 + Math.floor(Math.random() * 220)
  const tokensPerSec = 28 + Math.floor(Math.random() * 40)
  const primary = agentById(primaryAgent)

  const prefix = retry ? 'Retry · ' : ''
  const modeNote =
    mode === 'ask'
      ? 'Ask mode — read-only; no edits or shell.'
      : mode === 'edit'
        ? 'Edit only — file edits may need approval; no shell (demo).'
        : 'Automatic — edits & commands auto-approved (demo).'
  const agentNote = `Agent: **${primary.name}**.`

  const messages: ChatMessage[] = []

  const blocks: ChatMessage['blocks'] = [
    {
      type: 'markdown',
      text: `${prefix}Demo reply via **${model}** · ${agentNote}\n\n${modeNote}\n\n> ${userText.slice(0, 200)}${userText.length > 200 ? '…' : ''}`,
    },
  ]

  if (tools.includes('web_search')) {
    blocks.push({
      type: 'web_search',
      webSearch: {
        query: userText.slice(0, 80) || 'everflow playground',
        results: [
          {
            title: 'Everflow docs (demo)',
            url: 'https://example.com/everflow',
            snippet: 'Platform playground chat, agents, and sandbox tools.',
          },
          {
            title: 'PatternFly components',
            url: 'https://www.patternfly.org/',
            snippet: 'UI kit used by the Everflow platform UI.',
          },
        ],
      },
    })
  }

  if (tools.includes('terminal')) {
    blocks.push({
      type: 'terminal',
      terminal: {
        command: `echo "demo: ${userText.slice(0, 40).replace(/"/g, '')}"`,
        output: 'demo: ok',
        exitCode: 0,
      },
    })
  }

  if (mode === 'edit') {
    // Demo HITL: pending permission card so Once/Always/Reject UI is visible offline
    blocks.push({
      type: 'permission',
      permission: {
        id: `demo-perm-${Date.now()}`,
        title: 'edit demo.tsx',
        detail: `Apply demo patch for: ${userText.slice(0, 60)}`,
        status: 'pending',
      },
    })
  }

  if (mode === 'auto' && tools.includes('sandbox_fs')) {
    blocks.push({
      type: 'tool',
      tool: {
        title: 'sandbox_str_replace · demo.tsx',
        body: `+ // demo edit for: ${userText.slice(0, 60)}`,
        status: 'done',
      },
    })
  }

  messages.push({
    id: newMessageId('a'),
    role: 'assistant',
    agent: primary,
    text: `${prefix}Demo reply via ${model}. Wire to everflow-ai-workspace later.`,
    blocks,
    metrics: {
      ttftMs: ttftMs + 40,
      tokensPerSec,
      completionTokens: 80 + Math.floor(userText.length / 3),
    },
    createdAt: new Date().toISOString(),
  })

  return messages
}

export function emptyConversation(title = 'New chat'): ChatConversation {
  return {
    id: `n${Date.now()}`,
    title,
    meta: 'Just now',
    pinned: false,
    agents: DEFAULT_CHAT_AGENTS.map((id) => agentById(id)),
    primaryAgent: DEFAULT_PRIMARY_AGENT,
    messages: [],
    metrics: defaultMetrics(0),
    chatMode: DEFAULT_CHAT_MODE,
  }
}

export function updateConvMetrics(
  conv: ChatConversation,
  lastAssistant?: ChatMessage,
): ChatConversation {
  const m = lastAssistant?.metrics
  // Prefer provider-reported context (OpenCode tokens.total); fall back to estimate
  const estimated = recomputeContext(conv.messages)
  // Also scan all messages for the latest provider context total
  let fromProvider: number | undefined = m?.contextUsedTokens
  if (fromProvider == null) {
    for (let i = conv.messages.length - 1; i >= 0; i--) {
      const c = conv.messages[i]?.metrics?.contextUsedTokens
      if (c != null && c > 0) {
        fromProvider = c
        break
      }
    }
  }
  const contextUsedTokens = fromProvider ?? estimated
  return {
    ...conv,
    metrics: {
      contextUsedTokens,
      contextWindowTokens: conv.metrics.contextWindowTokens || DEFAULT_CONTEXT_WINDOW,
      tokensPerSec: m?.tokensPerSec ?? conv.metrics.tokensPerSec ?? 0,
      ttftMs: m?.ttftMs ?? conv.metrics.ttftMs ?? 0,
    },
    meta: 'Just now',
  }
}

export { CHAT_AGENTS, deriveTitleFromMessages, newMessageId }
