import {
  CHAT_AGENTS,
  DEFAULT_CHAT_AGENTS,
  DEFAULT_CHAT_MODE,
  DEFAULT_CONTEXT_WINDOW,
  agentById,
} from '@/data/chatCatalog'
import { defaultMetrics, seedConversationsForProject } from '@/data/chatShowcase'
import { PROJECTS } from '@/data/projects'
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
    }
  }
  return {
    convId: conv.id,
    title: conv.title,
    messages: cloneMessages(conv.messages),
    chatMode: conv.chatMode,
    enabledAgents: conv.agents.map((a) => a.id),
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
  agents: string[]
  retry?: boolean
}): ChatMessage[] {
  const {
    userText,
    model,
    mode,
    tools,
    agents,
    retry = false,
  } = opts
  const ttftMs = 120 + Math.floor(Math.random() * 220)
  const tokensPerSec = 28 + Math.floor(Math.random() * 40)
  const primaryAgentId = agents[0] || 'general'
  const primary = agentById(primaryAgentId)

  const prefix = retry ? 'Retry · ' : ''
  const modeNote =
    mode === 'ask'
      ? 'Ask mode — no file edits applied.'
      : mode === 'edit'
        ? 'Edit only — proposed a patch (demo).'
        : 'Automatic — agents may use tools.'

  const messages: ChatMessage[] = []

  if (mode === 'auto' && agents.length > 1) {
    const planner = agentById(agents.includes('planner') ? 'planner' : agents[0])
    messages.push({
      id: newMessageId('a'),
      role: 'assistant',
      agent: planner,
      thinking: 'Planning handoff…',
      blocks: [
        {
          type: 'markdown',
          text: `${prefix}**${planner.name}**: Breaking down “${userText.slice(0, 80)}${userText.length > 80 ? '…' : ''}”.\n\n${modeNote}`,
        },
      ],
      metrics: { ttftMs, tokensPerSec, completionTokens: 64 },
      createdAt: new Date().toISOString(),
    })
  }

  const blocks: ChatMessage['blocks'] = [
    {
      type: 'markdown',
      text: `${prefix}Demo reply via **${model}**.\n\n${modeNote}\n\n> ${userText.slice(0, 200)}${userText.length > 200 ? '…' : ''}`,
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

  if (mode === 'edit' || (mode === 'auto' && tools.includes('sandbox_fs'))) {
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
    messages: [],
    metrics: defaultMetrics(0),
    chatMode: DEFAULT_CHAT_MODE,
  }
}

export function updateConvMetrics(
  conv: ChatConversation,
  lastAssistant?: ChatMessage,
): ChatConversation {
  const contextUsedTokens = recomputeContext(conv.messages)
  const m = lastAssistant?.metrics
  return {
    ...conv,
    metrics: {
      contextUsedTokens,
      contextWindowTokens: DEFAULT_CONTEXT_WINDOW,
      tokensPerSec: m?.tokensPerSec ?? conv.metrics.tokensPerSec,
      ttftMs: m?.ttftMs ?? conv.metrics.ttftMs,
    },
    meta: 'Just now',
  }
}

export { CHAT_AGENTS, deriveTitleFromMessages, newMessageId }
