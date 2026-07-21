import type { ChatMessage } from '@/types/panels'
import { mapOcMessage } from './mapParts'
import type { OcEvent, OcMessageBundle, OcPart } from './types'

export type StreamPatch =
  | { kind: 'message'; message: ChatMessage }
  | { kind: 'part_delta'; messageId: string; partType: string; text: string }
  | { kind: 'part_set'; messageId: string; partType: string; text: string }
  | { kind: 'permission'; sessionId: string; permissionId: string; title: string; detail?: string }
  | { kind: 'session_status'; sessionId: string; status: string }
  | { kind: 'reload_messages' }
  | { kind: 'noop' }

/**
 * Map OpenCode bus events to UI patches. Schema is defensive — OpenCode versions
 * differ slightly (message.part.delta vs nested properties).
 */
export function mapOcEvent(ev: OcEvent): StreamPatch {
  const type = String(ev.type || '')
  const props = (ev.properties || {}) as Record<string, unknown>

  if (type === 'server.connected' || type === 'server.error') return { kind: 'noop' }

  // Full message payloads
  if (
    type.includes('message.updated') ||
    type.includes('message.created') ||
    type === 'message'
  ) {
    const info = (props.info || props.message || props) as OcMessageBundle['info']
    const parts = (props.parts || []) as OcPart[]
    if (info && typeof info === 'object' && 'id' in info) {
      return {
        kind: 'message',
        message: mapOcMessage({ info: info as OcMessageBundle['info'], parts }),
      }
    }
    // Sometimes the whole message is under properties
    if (props.sessionID || props.role) {
      const bundle = normalizeLooseMessage(props)
      if (bundle) return { kind: 'message', message: mapOcMessage(bundle) }
    }
    return { kind: 'reload_messages' }
  }

  // Streaming part deltas / updates (token streaming)
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
    if (messageId && delta != null && String(delta).length > 0) {
      return {
        kind: 'part_delta',
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
          messageId,
          partType,
          text: String(fullText),
        }
      }
      return {
        kind: 'part_set',
        messageId,
        partType,
        text: String(fullText),
      }
    }
    return { kind: 'reload_messages' }
  }

  if (type.includes('permission') && !type.includes('replied')) {
    const permissionId = String(
      props.permissionID || props.id || props.permissionId || '',
    )
    const sessionId = String(props.sessionID || props.sessionId || '')
    const title = String(props.permission || props.title || 'Permission required')
    const detail = props.pattern
      ? String(props.pattern)
      : props.patterns
        ? JSON.stringify(props.patterns)
        : undefined
    if (permissionId) {
      return { kind: 'permission', sessionId, permissionId, title, detail }
    }
  }

  if (type.includes('session.status') || type.includes('session.idle')) {
    return { kind: 'reload_messages' }
  }

  if (type.includes('session') || type.includes('message') || type.includes('tool')) {
    return { kind: 'reload_messages' }
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

export function upsertMessage(messages: ChatMessage[], msg: ChatMessage): ChatMessage[] {
  const withoutPending =
    msg.role === 'assistant'
      ? messages.filter((m) => !m.id.startsWith('pending-'))
      : messages
  const idx = withoutPending.findIndex((m) => m.id === msg.id)
  if (idx < 0) return [...withoutPending, msg]
  const out = [...withoutPending]
  out[idx] = msg
  return out
}
