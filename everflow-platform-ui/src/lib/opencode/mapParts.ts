import type {
  ChatAgentRef,
  ChatBlock,
  ChatMessage,
  ChatQuestionItem,
  ChatQuestionRequest,
} from '@/types/panels'
import type {
  OcMessageBundle,
  OcPart,
  OcQuestionInfo,
  OcQuestionRequest,
  OcSession,
  OcToolState,
} from './types'
import type { ChatConversation } from '@/types/panels'
import { DEFAULT_CHAT_MODE, DEFAULT_CONTEXT_WINDOW } from '@/data/chatCatalog'

function partText(p: OcPart): string {
  return String(p.text ?? p.content ?? '')
}

function toolState(p: OcPart): OcToolState | null {
  if (typeof p.state === 'object' && p.state) return p.state as OcToolState
  return null
}

function toolStatus(
  statusRaw: string,
): 'done' | 'running' | 'error' {
  const s = statusRaw.toLowerCase()
  if (s.includes('error') || s === 'error') return 'error'
  if (s.includes('run') || s === 'pending' || s === 'running') return 'running'
  return 'done'
}

function formatToolInput(input: Record<string, unknown> | undefined): string {
  if (!input || typeof input !== 'object') return ''
  const keys = Object.keys(input)
  if (keys.length === 0) return ''
  // Prefer readable single-field summaries
  if (typeof input.command === 'string') return input.command
  if (typeof input.filePath === 'string' || typeof input.path === 'string') {
    const path = String(input.filePath || input.path)
    const content =
      typeof input.content === 'string'
        ? input.content
        : typeof input.newString === 'string'
          ? input.newString
          : typeof input.oldString === 'string'
            ? `… → replace\n${input.oldString}`
            : ''
    if (content) {
      const clip = content.length > 3000 ? `${content.slice(0, 3000)}\n…` : content
      return `${path}\n\n${clip}`
    }
    return path
  }
  if (typeof input.pattern === 'string') {
    const glob = input.include || input.glob || input.path || ''
    return glob ? `${input.pattern}  (${glob})` : String(input.pattern)
  }
  if (typeof input.url === 'string') return String(input.url)
  if (typeof input.query === 'string') return String(input.query)
  try {
    const json = JSON.stringify(input, null, 2)
    return json.length > 4000 ? `${json.slice(0, 4000)}\n…` : json
  } catch {
    return String(input)
  }
}

function mapQuestionInfos(raw: OcQuestionInfo[] | undefined): ChatQuestionItem[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((q) => ({
      header: q.header ? String(q.header) : undefined,
      question: String(q.question || q.header || 'Choose an option'),
      options: (q.options || []).map((o) =>
        typeof o === 'string'
          ? { label: o }
          : {
              label: String(o.label || ''),
              description: o.description ? String(o.description) : undefined,
            },
      ).filter((o) => o.label),
      multiple: !!q.multiple,
      custom: q.custom !== false,
    }))
    .filter((q) => q.question)
}

/** Collapse duplicate question cards; prefer ones with a request id. */
function dedupeQuestionBlocksInPlace(blocks: ChatBlock[]): ChatBlock[] {
  const out: ChatBlock[] = []
  const seen = new Set<string>()
  let keptOrphan = false
  const hasRequestIdCard = blocks.some(
    (b) => b.type === 'question' && b.questionRequest?.id,
  )
  for (const b of blocks) {
    if (b.type !== 'question') {
      out.push(b)
      continue
    }
    const rid = b.questionRequest?.id
    if (!rid) {
      // Orphan chips without API id — only keep if no real request exists
      if (!hasRequestIdCard && !keptOrphan) {
        out.push(b)
        keptOrphan = true
      }
      continue
    }
    if (seen.has(rid)) continue
    seen.add(rid)
    out.push(b)
  }
  return out
}

/** Build a UI question block from an OpenCode question request (SSE or GET /question). */
export function mapQuestionRequest(req: OcQuestionRequest): ChatBlock {
  const items = mapQuestionInfos(req.questions)
  const first = items[0]
  const options = first?.options.map((o) => o.label) || []
  const qr: ChatQuestionRequest = {
    id: String(req.id),
    items:
      items.length > 0
        ? items
        : [{ question: 'Choose an option', options: [] }],
    status: 'pending',
  }
  return {
    type: 'question',
    text: first
      ? [first.header, first.question].filter(Boolean).join(' — ')
      : 'Choose an option',
    options,
    questionRequest: qr,
    partId: `question-${req.id}`,
  }
}

export function mapPartToBlocks(p: OcPart): ChatBlock[] {
  const t = (p.type || '').toLowerCase()
  const partId = p.id ? String(p.id) : undefined
  const callId = p.callID ? String(p.callID) : undefined

  // OpenCode stream bookends / internal — not user-visible content
  if (
    t === 'step-start' ||
    t === 'step-finish' ||
    t === 'snapshot' ||
    t === 'compaction' ||
    t === 'retry' ||
    t === 'agent'
  ) {
    return []
  }

  if (t === 'text' || t === 'markdown') {
    const text = partText(p)
    if (!text) return []
    return [{ type: 'markdown', text, partId }]
  }

  if (t === 'reasoning' || t === 'thinking') {
    // handled at message level as thinking
    return []
  }

  if (t === 'tool' || t === 'tool-invocation' || t === 'tool_use' || t === 'tool-call') {
    const st = toolState(p)
    const toolName = String(p.tool || p.name || 'tool').toLowerCase()
    const statusRaw =
      typeof p.state === 'string'
        ? p.state
        : st?.status || ''
    const status = toolStatus(statusRaw)
    const input = st?.input || (typeof p.input === 'object' && p.input
      ? (p.input as Record<string, unknown>)
      : undefined)

    // Interactive UI comes only from question.asked / GET /question (has request id).
    // Mapping the tool part into another question card causes a duplicate in the UI.
    if (toolName === 'question') {
      if (status === 'running' || status === 'error') {
        // Suppress — the SSE question card (or hydrate listQuestions) owns the UX.
        return []
      }
      // Completed: compact non-interactive summary only (no option chips)
      const nested = input?.questions as OcQuestionInfo[] | undefined
      const first = Array.isArray(nested) && nested[0] ? nested[0] : null
      const summary =
        (typeof st?.output === 'string' && st.output) ||
        (first
          ? [first.header, first.question].filter(Boolean).join(' — ')
          : st?.title || 'question')
      return [
        {
          type: 'tool',
          partId: partId || callId,
          tool: {
            title: 'question',
            body: String(summary).slice(0, 500),
            status: 'done',
            name: toolName,
            callId,
          },
        },
      ]
    }

    // Shell tools → terminal card
    if (toolName === 'bash' || toolName === 'shell' || toolName === 'terminal') {
      const command = String(
        input?.command || st?.title || p.command || p.title || 'bash',
      )
      const output =
        (typeof st?.output === 'string' && st.output) ||
        (typeof p.output === 'string' ? p.output : '') ||
        (status === 'error' && st?.error ? st.error : '') ||
        (status === 'running' ? '…' : '')
      return [
        {
          type: 'terminal',
          partId: partId || callId,
          terminal: {
            command,
            output: String(output).slice(0, 8000),
            exitCode: status === 'error' ? 1 : status === 'done' ? 0 : undefined,
          },
        },
      ]
    }

    // Web tools
    if (toolName === 'websearch' || toolName === 'web_search') {
      return [
        {
          type: 'web_search',
          partId: partId || callId,
          webSearch: {
            query: String(input?.query || st?.title || 'search'),
            results: [],
          },
        },
      ]
    }
    if (toolName === 'webfetch') {
      return [
        {
          type: 'tool',
          partId: partId || callId,
          tool: {
            title: st?.title || `webfetch · ${input?.url || ''}`.trim(),
            body:
              (typeof st?.output === 'string' && st.output.slice(0, 4000)) ||
              String(input?.url || ''),
            status,
            name: toolName,
            callId,
          },
        },
      ]
    }

    // File tools (read / write / edit / apply_patch / glob / grep)
    let body = ''
    if (typeof st?.output === 'string' && st.output) body = st.output
    else if (typeof p.output === 'string') body = p.output
    else if (status === 'error' && st?.error) body = st.error
    else body = formatToolInput(input)

    if (body.length > 8000) body = `${body.slice(0, 8000)}\n…`

    const pathHint = String(
      input?.filePath || input?.path || input?.file || '',
    )
    const title =
      st?.title ||
      (pathHint ? `${toolName} · ${pathHint}` : toolName)

    return [
      {
        type: 'tool',
        partId: partId || callId,
        tool: {
          title,
          body,
          status,
          name: toolName,
          callId,
        },
      },
    ]
  }

  if (t === 'question') {
    // Legacy / rare part-shaped questions
    if (Array.isArray(p.questions) && p.questions.length) {
      return [
        mapQuestionRequest({
          id: String(p.id || callId || `q-${Math.random().toString(36).slice(2, 8)}`),
          questions: p.questions,
        }),
      ]
    }
    const text = String(p.question || p.header || partText(p) || 'Choose an option')
    const options = (p.options || []).map((o) =>
      typeof o === 'string' ? o : String(o.label || o.value || ''),
    )
    return [{ type: 'question', text, options: options.filter(Boolean), partId }]
  }

  if (t === 'permission' || t === 'permission-request') {
    return [
      {
        type: 'permission',
        partId,
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
    const filesRaw = (p as OcPart & { files?: unknown }).files
    const files = Array.isArray(filesRaw)
      ? filesRaw.map(String).join('\n')
      : ''
    return [
      {
        type: 'tool',
        partId,
        tool: {
          title: `File ${p.path || p.filename || ''}`.trim() || 'file',
          body: (partText(p) || files).slice(0, 4000),
          status: 'done',
          name: t,
        },
      },
    ]
  }

  if (t === 'bash' || t === 'shell' || t === 'terminal') {
    return [
      {
        type: 'terminal',
        partId,
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
        partId,
        webSearch: {
          query: String(p.title || p.url || 'search'),
          results: [],
        },
      },
    ]
  }

  // fallback
  const text = partText(p)
  if (text) return [{ type: 'markdown', text, partId }]
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

/** UI placeholders — must NOT count as a real model reply (would stop polling early). */
const REPLY_PLACEHOLDER_RE =
  /^_?(Thinking|Generating response|No response content|Working)[.…_]*_?$/i

function isReplyPlaceholder(text: string | undefined): boolean {
  const t = (text || '').trim()
  if (!t) return true
  return REPLY_PLACEHOLDER_RE.test(t)
}

/** True if message has real user-visible reply body (not only reasoning / placeholders). */
export function messageHasReplyText(m: ChatMessage): boolean {
  const main = (m.text || '').trim()
  if (main && !isReplyPlaceholder(main)) return true
  return (m.blocks || []).some((b) => {
    if (b.type !== 'text' && b.type !== 'markdown') return false
    const bt = (b.text || '').trim()
    return !!bt && !isReplyPlaceholder(bt)
  })
}

/** True if message shows tool / question / permission activity (not empty). */
export function messageHasActivity(m: ChatMessage): boolean {
  if (messageHasReplyText(m)) return true
  if ((m.thinking || '').trim()) return true
  return (m.blocks || []).some(
    (b) =>
      b.type === 'tool' ||
      b.type === 'terminal' ||
      b.type === 'web_search' ||
      b.type === 'question' ||
      b.type === 'permission' ||
      b.type === 'image' ||
      b.type === 'attachment',
  )
}

/** Whether a pending question is still waiting on the user. */
export function messageHasPendingQuestion(m: ChatMessage): boolean {
  return (m.blocks || []).some(
    (b) =>
      b.type === 'question' &&
      (!b.questionRequest || b.questionRequest.status === 'pending'),
  )
}

/** Whether poll can stop: generation finished, or real answer text is present. */
export function assistantTurnReady(m: ChatMessage | undefined): boolean {
  if (!m || m.role !== 'assistant') return false
  if (m.id.startsWith('pending-')) return false
  // Waiting on interactive question — not "ready" for poll end (user must answer)
  if (messageHasPendingQuestion(m)) return false
  if (m.generationStatus === 'error') return true
  // Still streaming / empty shell — keep polling (even if UI shows Thinking…)
  if (m.generationStatus === 'incomplete') return false
  // OpenCode marked the turn complete (time.completed / finish)
  if (m.generationStatus === 'complete') return true
  // Fallback when status missing: only stop if we have real answer text
  return messageHasReplyText(m)
}

/**
 * Merge a streamed OpenCode part into an existing ChatMessage (by partId/callId).
 * Used for message.part.updated with full tool/text parts.
 */
export function applyOcPartToMessage(
  message: ChatMessage,
  part: OcPart,
): ChatMessage {
  const t = (part.type || '').toLowerCase()
  if (t === 'reasoning' || t === 'thinking') {
    const chunk = partText(part)
    if (!chunk) return message
    // Prefer full text when part carries complete reasoning
    const prev = message.thinking || ''
    const thinking =
      chunk.length >= prev.length && chunk.startsWith(prev.slice(0, 32))
        ? chunk
        : prev
          ? prev + (prev.endsWith(chunk) ? '' : chunk)
          : chunk
    return {
      ...message,
      thinking,
      generationStatus:
        message.generationStatus === 'complete' ? 'complete' : 'incomplete',
    }
  }

  const newBlocks = mapPartToBlocks(part)
  if (!newBlocks.length) return message

  const blocks = [...(message.blocks || [])]
  for (const nb of newBlocks) {
    const key = nb.partId || nb.tool?.callId
    if (key) {
      const idx = blocks.findIndex(
        (b) => b.partId === key || b.tool?.callId === key,
      )
      if (idx >= 0) {
        blocks[idx] = nb
        continue
      }
    }
    // Same tool callId without partId
    if (nb.tool?.callId) {
      const idx = blocks.findIndex((b) => b.tool?.callId === nb.tool?.callId)
      if (idx >= 0) {
        blocks[idx] = nb
        continue
      }
    }
    blocks.push(nb)
  }

  const textFallback = blocks
    .filter((b) => b.type === 'text' || b.type === 'markdown')
    .map((b) => b.text || '')
    .join('\n')

  return {
    ...message,
    blocks,
    text: textFallback || message.text,
    generationStatus:
      message.generationStatus === 'complete' ? 'complete' : 'incomplete',
  }
}

function generationStatusFromInfo(
  info: OcMessageBundle['info'] | undefined,
  hasReply: boolean,
  hasThinking: boolean,
  partsLen: number,
): ChatMessage['generationStatus'] {
  if (!info) return hasReply ? 'complete' : 'incomplete'
  const err = info.error
  if (err && typeof err === 'object' && (err as { message?: string }).message) {
    return 'error'
  }
  if (typeof err === 'string' && err) return 'error'
  const time = info.time as { created?: number; completed?: number } | undefined
  const finish = (info as { finish?: string }).finish
  if (time?.completed != null || finish) {
    return hasReply || err ? (err ? 'error' : 'complete') : 'complete'
  }
  if (hasReply && partsLen > 0) {
    // Has text but not marked complete yet — still streaming possible
    return 'incomplete'
  }
  if (hasThinking || partsLen === 0) return 'incomplete'
  return 'incomplete'
}

function normalizeEpochMs(t: number | undefined): number | undefined {
  if (t == null || !Number.isFinite(t)) return undefined
  // OpenCode sometimes uses µs-scale ids; times are usually ms already
  return t < 1e12 ? t * 1000 : t
}

function metricsFromOpenCodeInfo(
  info: OcMessageBundle['info'] | undefined,
  clientTtftMs?: number,
): ChatMessage['metrics'] | undefined {
  if (!info) return undefined
  const tokens = info.tokens as
    | {
        total?: number
        input?: number
        output?: number
        reasoning?: number
        cache?: { read?: number; write?: number }
      }
    | undefined
  const time = info.time as { created?: number; completed?: number } | undefined
  const created = normalizeEpochMs(time?.created)
  const completed = normalizeEpochMs(time?.completed)
  const output = tokens?.output
  let tokensPerSec: number | undefined
  let durationMs: number | undefined
  if (created != null && completed != null && completed > created) {
    durationMs = completed - created
    if (output != null && output > 0) {
      tokensPerSec = Math.max(1, Math.round((output / durationMs) * 1000))
    }
  }
  let contextUsedTokens: number | undefined
  if (tokens?.total != null && tokens.total > 0) {
    contextUsedTokens = tokens.total
  } else if (tokens) {
    const cacheRead = tokens.cache?.read ?? 0
    const sum =
      (tokens.input ?? 0) +
      (tokens.output ?? 0) +
      (tokens.reasoning ?? 0) +
      cacheRead
    if (sum > 0) contextUsedTokens = sum
  }
  if (
    clientTtftMs == null &&
    tokensPerSec == null &&
    output == null &&
    contextUsedTokens == null
  ) {
    return undefined
  }
  return {
    ttftMs: clientTtftMs,
    tokensPerSec,
    completionTokens: output,
    contextUsedTokens,
    durationMs,
  }
}

export function mapOcMessage(
  bundle: OcMessageBundle,
  opts?: { clientTtftMs?: number },
): ChatMessage {
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
  const text =
    textFallback ||
    (role === 'user'
      ? (bundle.parts || []).map((p) => partText(p)).find((t) => t) || undefined
      : undefined)

  const hasReply =
    (!!text && !isReplyPlaceholder(text)) ||
    blocks.some(
      (b) =>
        (b.type === 'text' || b.type === 'markdown') &&
        !!(b.text || '').trim() &&
        !isReplyPlaceholder(b.text),
    )
  const hasVisibleActivity = blocks.some(
    (b) =>
      b.type === 'tool' ||
      b.type === 'terminal' ||
      b.type === 'web_search' ||
      b.type === 'question' ||
      b.type === 'permission' ||
      b.type === 'image' ||
      b.type === 'attachment',
  )

  let errorText: string | undefined
  const err = bundle.info?.error
  if (typeof err === 'string') errorText = err
  else if (err && typeof err === 'object' && 'message' in err) {
    errorText = String((err as { message?: string }).message || '')
  }

  const generationStatus =
    role === 'assistant'
      ? generationStatusFromInfo(
          bundle.info,
          hasReply || hasVisibleActivity,
          !!thinking,
          (bundle.parts || []).length,
        )
      : 'complete'

  // No fake markdown placeholders — incomplete turns use empty body + stream status in UI
  // Dedupe question cards (at most one per request id; drop orphans without id)
  let finalBlocks = blocks.length > 0 ? dedupeQuestionBlocksInPlace(blocks) : undefined
  let finalText = text
  if (role === 'assistant' && errorText && !hasReply && !hasVisibleActivity) {
    finalBlocks = [{ type: 'markdown', text: `**Error:** ${errorText}` }]
    finalText = errorText
  } else if (!finalBlocks && text && !isReplyPlaceholder(text)) {
    finalBlocks = [{ type: role === 'user' ? 'text' : 'markdown', text }]
  } else if (
    role === 'assistant' &&
    !hasReply &&
    !hasVisibleActivity &&
    generationStatus === 'complete' &&
    !thinking
  ) {
    finalBlocks = [{ type: 'markdown', text: '*(No response content)*' }]
  }

  const baseMetrics = metricsFromOpenCodeInfo(bundle.info, opts?.clientTtftMs)

  return {
    id,
    role,
    agent,
    thinking: thinking || undefined,
    blocks: finalBlocks,
    text: finalText && !isReplyPlaceholder(finalText) ? finalText : undefined,
    metrics: baseMetrics,
    createdAt: bundle.info?.time?.created
      ? new Date(
          normalizeEpochMs(bundle.info.time.created) ?? bundle.info.time.created,
        ).toISOString()
      : undefined,
    generationStatus,
    errorText,
  }
}

export function mapOcMessages(
  list: OcMessageBundle[],
  opts?: { clientTtftMs?: number },
): ChatMessage[] {
  return list.map((b) => mapOcMessage(b, opts)).filter((m) => m.id)
}

/**
 * Live tok/s while streaming: prefer OpenCode output tokens, else estimate from text.
 */
export function estimateLiveTokensPerSec(
  message: ChatMessage | undefined,
  elapsedMs: number,
): number | undefined {
  if (!message || elapsedMs < 50) return undefined
  const out = message.metrics?.completionTokens
  if (out != null && out > 0) {
    return Math.max(1, Math.round((out / elapsedMs) * 1000))
  }
  const text = message.text || message.blocks?.map((b) => b.text || '').join('') || ''
  if (!text.trim()) return undefined
  // ~4 chars/token rough estimate for streaming display
  const est = Math.max(1, Math.round(text.length / 4))
  return Math.max(1, Math.round((est / elapsedMs) * 1000))
}

/**
 * Merge server history with local optimistic messages.
 * Keeps pending assistant until server has a **contentful** complete reply.
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

  const lastAsst = [...server].reverse().find((m) => m.role === 'assistant')
  const serverHasReadyAsst = assistantTurnReady(lastAsst)

  const extras = local.filter((m) => {
    if (m.id.startsWith('local-') && m.role === 'user') {
      const t = (m.text || '').trim()
      return t ? !serverTexts.has(t) : true
    }
    if (m.id.startsWith('pending-')) {
      // Keep local thinking placeholder until server assistant is ready
      return !serverHasReadyAsst
    }
    return false
  })

  // Prefer server messages; if last assistant is incomplete, still show it
  // (with generating hint) and optionally keep pending only if server asst missing
  if (!lastAsst && extras.some((m) => m.id.startsWith('pending-'))) {
    return [...server, ...extras]
  }
  if (lastAsst && !serverHasReadyAsst) {
    // Drop duplicate pending; server incomplete message already shows Thinking/Generating
    return server
  }
  return [...server, ...extras.filter((m) => !m.id.startsWith('pending-') || !serverHasReadyAsst)]
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
