import type { ChatMessage } from '@/types/panels'
import { mapOcMessage } from './mapParts'
import type { OcEvent, OcMessageBundle, OcPart } from './types'

export type StreamPatch =
  | { kind: 'message'; message: ChatMessage }
  | { kind: 'part_delta'; messageId: string; partType: string; text: string }
  | { kind: 'permission'; sessionId: string; permissionId: string; title: string; detail?: string }
  | { kind: 'session_status'; sessionId: string; status: string }
  | { kind: 'reload_messages' }
  | { kind: 'noop' }

/**
 * Map OpenCode bus events to UI patches. Schema is defensive — unknown events
 * trigger a full message reload when they look session-related.
 */
export function mapOcEvent(ev: OcEvent): StreamPatch {
  const type = String(ev.type || '')
  const props = (ev.properties || {}) as Record<string, unknown>

  if (type === 'server.connected') return { kind: 'noop' }

  // Message created / updated with full payload
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
    return { kind: 'reload_messages' }
  }

  // Streaming part deltas
  if (
    type.includes('message.part') ||
    type.includes('part.updated') ||
    type.includes('part.delta') ||
    type === 'text-delta' ||
    type.includes('text.delta')
  ) {
    const messageId = String(
      props.messageID || props.messageId || (props.part as OcPart)?.id || '',
    )
    const part = (props.part || props) as OcPart
    const partType = String(part.type || props.type || 'text')
    const text = String(part.text || part.content || props.text || props.delta || '')
    if (messageId && text) {
      return { kind: 'part_delta', messageId, partType, text }
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

  if (type.includes('session') || type.includes('message') || type.includes('tool')) {
    return { kind: 'reload_messages' }
  }

  return { kind: 'noop' }
}

/** Apply a text delta onto an existing message list (immutable). */
export function applyPartDelta(
  messages: ChatMessage[],
  messageId: string,
  partType: string,
  text: string,
): ChatMessage[] {
  const idx = messages.findIndex((m) => m.id === messageId)
  if (idx < 0) {
    // Create streaming assistant placeholder
    const isReasoning = partType === 'reasoning' || partType === 'thinking'
    const msg: ChatMessage = {
      id: messageId,
      role: 'assistant',
      thinking: isReasoning ? text : undefined,
      blocks: isReasoning ? undefined : [{ type: 'markdown', text }],
      text: isReasoning ? undefined : text,
    }
    return [...messages, msg]
  }
  const prev = messages[idx]
  const isReasoning = partType === 'reasoning' || partType === 'thinking'
  let next: ChatMessage
  if (isReasoning) {
    next = { ...prev, thinking: (prev.thinking || '') + text }
  } else {
    const blocks = [...(prev.blocks || [])]
    const last = blocks[blocks.length - 1]
    if (last && (last.type === 'markdown' || last.type === 'text')) {
      blocks[blocks.length - 1] = { ...last, text: (last.text || '') + text }
    } else {
      blocks.push({ type: 'markdown', text })
    }
    next = {
      ...prev,
      blocks,
      text: (prev.text || '') + text,
    }
  }
  const out = [...messages]
  out[idx] = next
  return out
}

export function upsertMessage(messages: ChatMessage[], msg: ChatMessage): ChatMessage[] {
  const idx = messages.findIndex((m) => m.id === msg.id)
  if (idx < 0) return [...messages, msg]
  const out = [...messages]
  out[idx] = msg
  return out
}
