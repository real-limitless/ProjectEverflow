import type { ChatAgentRef, ChatBlock, ChatMessage } from '@/types/panels'
import type { OcMessageBundle, OcPart, OcSession } from './types'
import type { ChatConversation } from '@/types/panels'
import { DEFAULT_CHAT_MODE, DEFAULT_CONTEXT_WINDOW } from '@/data/chatCatalog'

function partText(p: OcPart): string {
  return String(p.text ?? p.content ?? '')
}

function mapPartToBlocks(p: OcPart): ChatBlock[] {
  const t = (p.type || '').toLowerCase()

  if (t === 'text' || t === 'markdown') {
    const text = partText(p)
    if (!text) return []
    return [{ type: t === 'markdown' ? 'markdown' : 'markdown', text }]
  }

  if (t === 'reasoning' || t === 'thinking') {
    // handled at message level as thinking
    return []
  }

  if (t === 'tool' || t === 'tool-invocation' || t === 'tool_use' || t === 'tool-call') {
    const title = String(p.tool || p.name || p.title || 'tool')
    let body = ''
    if (typeof p.output === 'string') body = p.output
    else if (p.output != null) body = JSON.stringify(p.output, null, 2)
    else if (typeof p.state === 'object' && p.state && 'output' in p.state) {
      body = String((p.state as { output?: string }).output || '')
    } else if (p.input != null) body = JSON.stringify(p.input, null, 2)
    const statusRaw =
      typeof p.state === 'string'
        ? p.state
        : typeof p.state === 'object' && p.state
          ? String((p.state as { status?: string }).status || '')
          : ''
    const status =
      statusRaw.includes('error') || statusRaw === 'error'
        ? 'error'
        : statusRaw.includes('run') || statusRaw === 'pending'
          ? 'running'
          : 'done'
    return [{ type: 'tool', tool: { title, body, status } }]
  }

  if (t === 'question') {
    const text = String(p.question || p.header || partText(p) || 'Choose an option')
    const options = (p.options || []).map((o) =>
      typeof o === 'string' ? o : String(o.label || o.value || ''),
    )
    return [{ type: 'question', text, options: options.filter(Boolean) }]
  }

  if (t === 'permission' || t === 'permission-request') {
    return [
      {
        type: 'permission',
        permission: {
          id: String(p.permissionID || p.id || ''),
          title: String(p.permission || p.title || 'Permission required'),
          detail: partText(p) || undefined,
          patterns: p.patterns,
          status: 'pending',
        },
      },
    ]
  }

  if (t === 'file' || t === 'patch') {
    return [
      {
        type: 'tool',
        tool: {
          title: `File ${p.path || p.filename || ''}`.trim(),
          body: partText(p).slice(0, 4000),
          status: 'done',
        },
      },
    ]
  }

  if (t === 'bash' || t === 'shell' || t === 'terminal') {
    return [
      {
        type: 'terminal',
        terminal: {
          command: String(p.command || p.title || ''),
          output: partText(p) || String(p.output || ''),
          exitCode: typeof p.exit === 'number' ? p.exit : undefined,
        },
      },
    ]
  }

  if (t === 'web_search' || t === 'websearch' || t === 'webfetch') {
    return [
      {
        type: 'web_search',
        webSearch: {
          query: String(p.title || p.url || 'search'),
          results: [],
        },
      },
    ]
  }

  // fallback
  const text = partText(p)
  if (text) return [{ type: 'markdown', text }]
  return []
}

/** Coerce unknown API item into { info, parts }. */
export function normalizeMessageBundle(raw: unknown): OcMessageBundle | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>

  // Already { info, parts }
  if (o.info && typeof o.info === 'object') {
    const info = o.info as OcMessageBundle['info']
    const parts = Array.isArray(o.parts) ? (o.parts as OcPart[]) : []
    if (!info.id) {
      info.id = `oc-${Math.random().toString(36).slice(2, 10)}`
    }
    return { info, parts }
  }

  // Flat message: { id, role, parts } or { id, role, content }
  if (o.id || o.role) {
    const parts: OcPart[] = Array.isArray(o.parts)
      ? (o.parts as OcPart[])
      : o.content != null || o.text != null
        ? [{ type: 'text', text: String(o.content ?? o.text ?? '') }]
        : []
    return {
      info: {
        id: String(o.id || `oc-${Math.random().toString(36).slice(2, 10)}`),
        role: String(o.role || 'assistant'),
        agent: typeof o.agent === 'string' ? o.agent : undefined,
        time:
          typeof o.time === 'object' && o.time
            ? (o.time as OcMessageBundle['info']['time'])
            : undefined,
      },
      parts,
    }
  }

  return null
}

/** Accept bare arrays or common wrappers from OpenCode / proxies. */
export function normalizeMessageList(data: unknown): OcMessageBundle[] {
  if (data == null) return []
  let list: unknown[] = []
  if (Array.isArray(data)) {
    list = data
  } else if (typeof data === 'object') {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.data)) list = o.data
    else if (Array.isArray(o.messages)) list = o.messages
    else if (Array.isArray(o.items)) list = o.items
    else return []
  }
  const out: OcMessageBundle[] = []
  for (const item of list) {
    const b = normalizeMessageBundle(item)
    if (b) out.push(b)
  }
  return out
}

export function mapOcMessage(bundle: OcMessageBundle): ChatMessage {
  const roleRaw = (bundle.info?.role || 'assistant').toLowerCase()
  const role: ChatMessage['role'] =
    roleRaw === 'user' ? 'user' : roleRaw === 'system' ? 'system' : 'assistant'

  let thinking = ''
  const blocks: ChatBlock[] = []
  for (const p of bundle.parts || []) {
    const t = (p.type || '').toLowerCase()
    if (t === 'reasoning' || t === 'thinking') {
      thinking += (thinking ? '\n' : '') + partText(p)
      continue
    }
    blocks.push(...mapPartToBlocks(p))
  }

  const textFallback =
    blocks
      .filter((b) => b.type === 'text' || b.type === 'markdown')
      .map((b) => b.text || '')
      .join('\n') ||
    // Some payloads only have thinking or tools — still show something for user role
    (role === 'user' && !blocks.length
      ? (bundle.parts || []).map((p) => partText(p)).filter(Boolean).join('\n')
      : '')

  let agent: ChatAgentRef | undefined
  if (bundle.info?.agent) {
    agent = {
      id: bundle.info.agent,
      name: bundle.info.agent,
      role: 'general',
    }
  }

  const id = bundle.info?.id || `oc-${Math.random().toString(36).slice(2)}`
  // User messages with only text and no blocks still need text
  const text =
    textFallback ||
    (role === 'user'
      ? (bundle.parts || []).map((p) => partText(p)).find((t) => t) || undefined
      : undefined)

  return {
    id,
    role,
    agent,
    thinking: thinking || undefined,
    blocks:
      blocks.length > 0
        ? blocks
        : text
          ? [{ type: role === 'user' ? 'text' : 'markdown', text }]
          : undefined,
    text,
    createdAt: bundle.info?.time?.created
      ? new Date(
          typeof bundle.info.time.created === 'number' && bundle.info.time.created < 1e12
            ? bundle.info.time.created * 1000
            : bundle.info.time.created,
        ).toISOString()
      : undefined,
  }
}

export function mapOcMessages(list: OcMessageBundle[]): ChatMessage[] {
  return list.map(mapOcMessage).filter((m) => m.id)
}

/**
 * Merge server history with local optimistic messages.
 * Keeps local user messages that are not yet reflected on the server.
 */
export function mergeServerMessages(
  server: ChatMessage[],
  local: ChatMessage[],
): ChatMessage[] {
  if (!server.length) return local.length ? local : server
  if (!local.length) return server

  const serverTexts = new Set(
    server
      .filter((m) => m.role === 'user')
      .map((m) => (m.text || '').trim())
      .filter(Boolean),
  )
  const extras = local.filter((m) => {
    if (!m.id.startsWith('local-') && !m.id.startsWith('pending-')) return false
    if (m.role === 'user') {
      const t = (m.text || '').trim()
      return t ? !serverTexts.has(t) : true
    }
    // Keep local pending assistant placeholder only if server has no newer assistant
    return m.id.startsWith('pending-')
  })
  // If server already has assistant after last user, drop pending placeholders
  const lastServer = server[server.length - 1]
  const pending = extras.filter((m) => {
    if (!m.id.startsWith('pending-')) return true
    return !(lastServer && lastServer.role === 'assistant')
  })
  return [...server, ...pending]
}

export function sessionToConversation(
  session: OcSession,
  messages: ChatMessage[] = [],
): ChatConversation {
  const title = session.title || 'Chat'
  return {
    id: session.id,
    title,
    meta: 'OpenCode',
    pinned: false,
    agents: [],
    messages,
    metrics: {
      contextUsedTokens: 0,
      contextWindowTokens: DEFAULT_CONTEXT_WINDOW,
      tokensPerSec: 0,
      ttftMs: 0,
    },
    chatMode: DEFAULT_CHAT_MODE,
    source: 'opencode',
  }
}

export function parseModelId(modelId: string): { providerID: string; modelID: string } | null {
  if (!modelId) return null
  if (modelId.includes('/')) {
    const [providerID, ...rest] = modelId.split('/')
    return { providerID, modelID: rest.join('/') }
  }
  // Heuristic for legacy catalog ids
  if (modelId.startsWith('grok') || modelId.startsWith('xai')) {
    return { providerID: 'xai', modelID: modelId }
  }
  if (modelId.startsWith('claude')) {
    return { providerID: 'anthropic', modelID: modelId }
  }
  if (modelId.startsWith('gpt') || modelId.startsWith('o1')) {
    return { providerID: 'openai', modelID: modelId }
  }
  return { providerID: 'openai', modelID: modelId }
}
