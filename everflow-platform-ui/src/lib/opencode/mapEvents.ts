import type { ChatBlock, ChatMessage } from '@/types/panels'
import {
  applyOcPartToMessage,
  mapOcMessage,
  mapQuestionRequest,
} from './mapParts'
import type { OcEvent, OcMessageBundle, OcPart, OcQuestionRequest } from './types'

export type StreamPatch =
  | { kind: 'message'; sessionId?: string; message: ChatMessage }
  | {
      kind: 'part_delta'
      sessionId?: string
      messageId: string
      partType: string
      text: string
    }
  | {
      kind: 'part_set'
      sessionId?: string
      messageId: string
      partType: string
      text: string
    }
  | { kind: 'part_full'; sessionId?: string; messageId: string; part: OcPart }
  | {
      kind: 'question'
      sessionId: string
      requestId: string
      questions: OcQuestionRequest['questions']
      messageId?: string
    }
  | { kind: 'question_resolved'; sessionId: string; requestId: string; status: 'answered' | 'rejected' }
  | { kind: 'permission'; sessionId: string; permissionId: string; title: string; detail?: string }
  | { kind: 'session_status'; sessionId: string; status: string }
  | { kind: 'reload_messages'; sessionId?: string }
  | { kind: 'noop' }

function eventSessionId(props: Record<string, unknown>): string {
  return String(props.sessionID || props.sessionId || props.session_id || '')
}

/**
 * Map OpenCode bus events to UI patches. Schema is defensive — OpenCode versions
 * differ slightly (message.part.delta vs nested properties).
 */
export function mapOcEvent(ev: OcEvent): StreamPatch {
  const type = String(ev.type || '')
  const props = (ev.properties || {}) as Record<string, unknown>

  if (type === 'server.connected' || type === 'server.error') return { kind: 'noop' }

  // Interactive questions (not message parts)
  if (
    type === 'question.asked' ||
    type === 'question.v2.asked' ||
    type.includes('question.asked') ||
    type.includes('question.v2.asked')
  ) {
    const requestId = String(props.id || props.requestID || props.requestId || '')
    const sessionId = String(props.sessionID || props.sessionId || '')
    const questions = Array.isArray(props.questions)
      ? (props.questions as OcQuestionRequest['questions'])
      : []
    const tool = props.tool as { messageID?: string; callID?: string } | undefined
    if (requestId && questions.length) {
      return {
        kind: 'question',
        sessionId,
        requestId,
        questions,
        messageId: tool?.messageID ? String(tool.messageID) : undefined,
      }
    }
    return { kind: 'reload_messages' }
  }

  if (
    type === 'question.replied' ||
    type === 'question.rejected' ||
    type === 'question.v2.replied' ||
    type === 'question.v2.rejected' ||
    type.includes('question.replied') ||
    type.includes('question.rejected')
  ) {
    const requestId = String(props.requestID || props.requestId || props.id || '')
    const sessionId = String(props.sessionID || props.sessionId || '')
    const status =
      type.includes('reject') ? ('rejected' as const) : ('answered' as const)
    if (requestId) {
      return { kind: 'question_resolved', sessionId, requestId, status }
    }
  }

  // Full message payloads
  if (
    type.includes('message.updated') ||
    type.includes('message.created') ||
    type === 'message'
  ) {
    const info = (props.info || props.message || props) as OcMessageBundle['info']
    const parts = (props.parts || []) as OcPart[]
    const hasParts = Array.isArray(props.parts)
    const sessionId = eventSessionId(props)
    if (info && typeof info === 'object' && 'id' in info) {
      // message.updated often carries only info (no parts) — do not wipe content
      if (!hasParts) {
        return {
          kind: 'message',
          sessionId,
          message: mapOcMessage({
            info: info as OcMessageBundle['info'],
            parts: [],
          }),
        }
      }
      return {
        kind: 'message',
        sessionId,
        message: mapOcMessage({ info: info as OcMessageBundle['info'], parts }),
      }
    }
    // Sometimes the whole message is under properties
    if (props.sessionID || props.role) {
      const bundle = normalizeLooseMessage(props)
      if (bundle) {
        return { kind: 'message', sessionId, message: mapOcMessage(bundle) }
      }
    }
    return { kind: 'reload_messages', sessionId }
  }

  // Streaming part deltas / updates (token streaming + full tool parts)
  if (
    type.includes('message.part') ||
    type.includes('part.updated') ||
    type.includes('part.delta') ||
    type === 'text-delta' ||
    type.includes('text.delta')
  ) {
    const partRaw = (props.part || props) as Record<string, unknown>
    const messageId = String(
      props.messageID ||
        props.messageId ||
        partRaw.messageID ||
        partRaw.messageId ||
        '',
    )
    const partType = String(partRaw.type || props.type || 'text')
    // Prefer incremental delta; fall back to full text (updated events)
    const delta = props.delta ?? partRaw.delta
    const fullText = partRaw.text ?? props.text

    // Full structured part (tool, file, …) — upsert whole part, not text only
    const structuredTypes = new Set([
      'tool',
      'tool-invocation',
      'tool_use',
      'tool-call',
      'file',
      'patch',
      'bash',
      'shell',
      'terminal',
      'web_search',
      'websearch',
      'webfetch',
      'question',
      'permission',
    ])
    const sessionId = eventSessionId(props)
    if (
      messageId &&
      partRaw &&
      typeof partRaw === 'object' &&
      structuredTypes.has(partType.toLowerCase())
    ) {
      return {
        kind: 'part_full',
        sessionId,
        messageId,
        part: partRaw as OcPart,
      }
    }

    if (messageId && delta != null && String(delta).length > 0) {
      return {
        kind: 'part_delta',
        sessionId,
        messageId,
        partType,
        text: String(delta),
      }
    }
    if (messageId && fullText != null) {
      // part.updated often carries the full part text so far
      if (type.includes('delta')) {
        return {
          kind: 'part_delta',
          sessionId,
          messageId,
          partType,
          text: String(fullText),
        }
      }
      return {
        kind: 'part_set',
        sessionId,
        messageId,
        partType,
        text: String(fullText),
      }
    }
    // Unknown part shape with message id — full hydrate
    if (messageId && partRaw && typeof partRaw === 'object' && partRaw.type) {
      return {
        kind: 'part_full',
        sessionId,
        messageId,
        part: partRaw as OcPart,
      }
    }
    return { kind: 'reload_messages', sessionId }
  }

  if (
    (type.includes('permission') && !type.includes('replied')) ||
    type === 'permission.asked' ||
    type === 'permission.v2.asked'
  ) {
    const permissionId = String(
      props.permissionID || props.id || props.permissionId || props.requestID || '',
    )
    const sessionId = String(props.sessionID || props.sessionId || '')
    const title = String(props.permission || props.title || 'Permission required')
    const detail = props.pattern
      ? String(props.pattern)
      : props.patterns
        ? JSON.stringify(props.patterns)
        : props.metadata
          ? JSON.stringify(props.metadata)
          : undefined
    if (permissionId) {
      return { kind: 'permission', sessionId, permissionId, title, detail }
    }
  }

  if (type.includes('session.status') || type.includes('session.idle')) {
    return { kind: 'reload_messages', sessionId: eventSessionId(props) }
  }

  if (type.includes('session') || type.includes('message') || type.includes('tool')) {
    return { kind: 'reload_messages', sessionId: eventSessionId(props) }
  }

  return { kind: 'noop' }
}

function normalizeLooseMessage(props: Record<string, unknown>): OcMessageBundle | null {
  if (!props.id && !props.role) return null
  return {
    info: {
      id: String(props.id || `oc-${Math.random().toString(36).slice(2)}`),
      role: String(props.role || 'assistant'),
      agent: typeof props.agent === 'string' ? props.agent : undefined,
      time: props.time as OcMessageBundle['info']['time'],
      finish: props.finish as string | undefined,
      tokens: props.tokens as OcMessageBundle['info']['tokens'],
    },
    parts: Array.isArray(props.parts) ? (props.parts as OcPart[]) : [],
  }
}

/** Apply a text delta onto an existing message list (immutable). */
export function applyPartDelta(
  messages: ChatMessage[],
  messageId: string,
  partType: string,
  text: string,
  mode: 'append' | 'set' = 'append',
): ChatMessage[] {
  const isReasoning = partType === 'reasoning' || partType === 'thinking'
  const idx = messages.findIndex((m) => m.id === messageId)
  if (idx < 0) {
    // Create streaming assistant placeholder with this content
    const msg: ChatMessage = {
      id: messageId,
      role: 'assistant',
      generationStatus: 'incomplete',
      thinking: isReasoning ? text : undefined,
      blocks: isReasoning
        ? undefined
        : text
          ? [{ type: 'markdown', text }]
          : undefined,
      text: isReasoning ? undefined : text || undefined,
    }
    // Drop local pending shells when real stream starts
    const withoutPending = messages.filter((m) => !m.id.startsWith('pending-'))
    return [...withoutPending, msg]
  }
  const prev = messages[idx]
  let next: ChatMessage
  if (isReasoning) {
    const thinking =
      mode === 'set' ? text : (prev.thinking || '') + text
    next = {
      ...prev,
      thinking,
      generationStatus: prev.generationStatus === 'complete' ? 'complete' : 'incomplete',
    }
  } else {
    const blocks = [...(prev.blocks || [])]
    const last = blocks[blocks.length - 1]
    if (last && (last.type === 'markdown' || last.type === 'text')) {
      blocks[blocks.length - 1] = {
        ...last,
        text: mode === 'set' ? text : (last.text || '') + text,
      }
    } else if (text) {
      blocks.push({ type: 'markdown', text })
    }
    const body =
      mode === 'set'
        ? text
        : (prev.text || '') + text
    next = {
      ...prev,
      blocks: blocks.length ? blocks : undefined,
      text: body || undefined,
      generationStatus: prev.generationStatus === 'complete' ? 'complete' : 'incomplete',
    }
  }
  const out = [...messages]
  out[idx] = next
  // Drop pending shells once real assistant stream is active
  return out.filter((m, i) => i === idx || !m.id.startsWith('pending-'))
}

/** Apply a full OpenCode part (esp. tools) onto the message list. */
export function applyPartFull(
  messages: ChatMessage[],
  messageId: string,
  part: OcPart,
): ChatMessage[] {
  const idx = messages.findIndex((m) => m.id === messageId)
  if (idx < 0) {
    const shell: ChatMessage = {
      id: messageId,
      role: 'assistant',
      generationStatus: 'incomplete',
    }
    const next = applyOcPartToMessage(shell, part)
    const withoutPending = messages.filter((m) => !m.id.startsWith('pending-'))
    return [...withoutPending, next]
  }
  const out = [...messages]
  out[idx] = applyOcPartToMessage(messages[idx], part)
  return out.filter((m, i) => i === idx || !m.id.startsWith('pending-'))
}

/**
 * Upsert an assistant message. When the incoming payload is info-only (empty
 * body) and we already have content/tools, preserve the existing body.
 */
export function upsertMessage(messages: ChatMessage[], msg: ChatMessage): ChatMessage[] {
  const withoutPending =
    msg.role === 'assistant'
      ? messages.filter((m) => !m.id.startsWith('pending-'))
      : messages
  const idx = withoutPending.findIndex((m) => m.id === msg.id)
  if (idx < 0) return [...withoutPending, msg]

  const prev = withoutPending[idx]
  const incomingEmpty =
    !(msg.blocks && msg.blocks.length) &&
    !(msg.text || '').trim() &&
    !(msg.thinking || '').trim()
  const prevHasBody =
    !!(prev.blocks && prev.blocks.length) ||
    !!(prev.text || '').trim() ||
    !!(prev.thinking || '').trim()

  let merged: ChatMessage
  if (incomingEmpty && prevHasBody) {
    // message.updated with info only — keep streamed parts
    merged = {
      ...prev,
      agent: msg.agent || prev.agent,
      metrics: msg.metrics || prev.metrics,
      createdAt: msg.createdAt || prev.createdAt,
      generationStatus: msg.generationStatus || prev.generationStatus,
      errorText: msg.errorText || prev.errorText,
      thinking: prev.thinking,
      blocks: prev.blocks,
      text: prev.text,
    }
  } else if (
    msg.blocks &&
    msg.blocks.length &&
    prev.blocks &&
    prev.blocks.length &&
    msg.blocks.length < prev.blocks.length &&
    !messageLooksComplete(msg)
  ) {
    // Prefer richer block list while still streaming
    merged = {
      ...msg,
      blocks: prev.blocks,
      text: msg.text || prev.text,
      thinking: msg.thinking || prev.thinking,
    }
  } else {
    merged = {
      ...prev,
      ...msg,
      // Never drop thinking if new payload omits it mid-stream
      thinking: msg.thinking || prev.thinking,
      blocks: msg.blocks?.length ? msg.blocks : prev.blocks,
      text: msg.text || prev.text,
    }
  }

  const out = [...withoutPending]
  out[idx] = merged
  return out
}

function messageLooksComplete(m: ChatMessage): boolean {
  return m.generationStatus === 'complete' || m.generationStatus === 'error'
}

/**
 * Drop orphan question cards that lack a request id (legacy tool-part mapping)
 * and collapse duplicate cards for the same request id — keep one.
 */
export function dedupeQuestionBlocks(blocks: ChatBlock[] | undefined): ChatBlock[] | undefined {
  if (!blocks?.length) return blocks
  const out: ChatBlock[] = []
  const seenRequestIds = new Set<string>()
  for (const b of blocks) {
    if (b.type !== 'question') {
      out.push(b)
      continue
    }
    const rid = b.questionRequest?.id
    // Orphans without request id cannot be answered via OpenCode API — drop them
    // once a real question card exists, or always prefer request-id cards.
    if (!rid) continue
    if (seenRequestIds.has(rid)) continue
    seenRequestIds.add(rid)
    out.push(b)
  }
  // If we dropped everything and had only orphans, keep a single orphan as last resort
  if (!out.some((b) => b.type === 'question')) {
    const firstOrphan = blocks.find((b) => b.type === 'question' && !b.questionRequest?.id)
    if (firstOrphan && !blocks.some((b) => b.type === 'question' && b.questionRequest?.id)) {
      // Only keep orphan when there is truly no request-id card in this list
      out.push(firstOrphan)
    }
  }
  return out
}

function stripOrphanQuestions(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .map((m) => {
      if (!m.blocks?.some((b) => b.type === 'question')) return m
      const blocks = dedupeQuestionBlocks(m.blocks)
      return { ...m, blocks }
    })
    .filter((m) => {
      // Drop empty standalone question shells (question-{id} with no blocks left)
      if (m.id.startsWith('question-') && !(m.blocks && m.blocks.length)) return false
      return true
    })
}

/** Insert or update a question card for the active session. */
export function upsertQuestionMessage(
  messages: ChatMessage[],
  patch: {
    requestId: string
    questions: OcQuestionRequest['questions']
    messageId?: string
  },
): ChatMessage[] {
  const block = mapQuestionRequest({
    id: patch.requestId,
    questions: patch.questions,
  })
  const qid = `question-${patch.requestId}`

  // Start from a clean slate: one request id → one card; drop tool-part orphans
  let base = stripOrphanQuestions(messages)

  // If a standalone question-{id} message exists AND we will attach to the
  // assistant message, remove the standalone to avoid two cards in the thread.
  if (patch.messageId) {
    base = base.filter((m) => m.id !== qid)
  }

  // Attach to the referenced assistant message when possible
  if (patch.messageId) {
    const idx = base.findIndex((m) => m.id === patch.messageId)
    if (idx >= 0) {
      const prev = base[idx]
      // Replace any existing question blocks with the single authoritative card
      const withoutQs = (prev.blocks || []).filter((b) => b.type !== 'question')
      const blocks = dedupeQuestionBlocks([...withoutQs, block]) || [block]
      const out = [...base]
      out[idx] = {
        ...prev,
        blocks,
        generationStatus: 'incomplete',
      }
      return out.filter((m) => !m.id.startsWith('pending-'))
    }
  }

  // Standalone question message (or update existing)
  const idx = base.findIndex(
    (m) =>
      m.id === qid ||
      (m.blocks || []).some(
        (b) => b.type === 'question' && b.questionRequest?.id === patch.requestId,
      ),
  )
  if (idx >= 0) {
    const prev = base[idx]
    const withoutQs = (prev.blocks || []).filter(
      (b) =>
        !(
          b.type === 'question' &&
          (b.questionRequest?.id === patch.requestId || !b.questionRequest?.id)
        ),
    )
    const blocks = dedupeQuestionBlocks([...withoutQs, block]) || [block]
    const out = [...base]
    out[idx] = { ...prev, blocks, generationStatus: 'incomplete' }
    // Also strip this request from any other messages
    return out
      .map((m, i) => {
        if (i === idx) return m
        if (!m.blocks?.some((b) => b.type === 'question')) return m
        return {
          ...m,
          blocks: m.blocks.filter(
            (b) =>
              !(
                b.type === 'question' &&
                (b.questionRequest?.id === patch.requestId || !b.questionRequest?.id)
              ),
          ),
        }
      })
      .filter((m) => !m.id.startsWith('pending-'))
      .filter((m) => !(m.id.startsWith('question-') && !(m.blocks && m.blocks.length)))
  }

  const msg: ChatMessage = {
    id: qid,
    role: 'assistant',
    generationStatus: 'incomplete',
    blocks: [block],
    createdAt: new Date().toISOString(),
  }
  return [
    ...base
      .filter((m) => !m.id.startsWith('pending-'))
      // Remove orphans / other copies of this request before appending
      .map((m) => {
        if (!m.blocks?.some((b) => b.type === 'question')) return m
        return {
          ...m,
          blocks: m.blocks.filter(
            (b) =>
              !(
                b.type === 'question' &&
                (b.questionRequest?.id === patch.requestId || !b.questionRequest?.id)
              ),
          ),
        }
      })
      .filter((m) => !(m.id.startsWith('question-') && !(m.blocks && m.blocks.length))),
    msg,
  ]
}

export function resolveQuestionMessage(
  messages: ChatMessage[],
  requestId: string,
  status: 'answered' | 'rejected',
): ChatMessage[] {
  return messages.map((m) => {
    if (!m.blocks?.some((b) => b.type === 'question')) return m
    let changed = false
    const blocks = m.blocks.map((b) => {
      if (b.type !== 'question' || b.questionRequest?.id !== requestId) return b
      changed = true
      return {
        ...b,
        questionRequest: b.questionRequest
          ? { ...b.questionRequest, status }
          : undefined,
      }
    })
    if (!changed) return m
    return {
      ...m,
      blocks,
      generationStatus: status === 'answered' ? m.generationStatus : 'complete',
    }
  })
}
