/**
 * OpenCode session recovery helpers for Chat.
 * UI may retain a ses_… id after harness restart; OpenCode returns 404 Not Found.
 */

import type { ChatConversation, ChatMessage } from '../../types/panels'
import type { OcSession } from './types'

/** True when OpenCode (or proxy) says the session id is unknown. */
export function isOpenCodeSessionMissingError(err: unknown): boolean {
  if (err == null) return false
  const status =
    typeof err === 'object' && err !== null && 'status' in err
      ? Number((err as { status: unknown }).status)
      : undefined
  if (status === 404) return true
  const msg =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : typeof err === 'object' && err !== null && 'message' in err
          ? String((err as { message: unknown }).message)
          : String(err)
  const lower = msg.toLowerCase()
  if (!lower.trim()) return false
  // Bare "Not Found" from HTTP statusText is the common Chat failure.
  if (lower === 'not found' || lower === '404' || lower === '404 not found') return true
  if (/\b404\b/.test(lower) && /not\s*found|session|unknown/i.test(lower)) return true
  if (/session\s+(not\s+found|unknown|missing|does\s+not\s+exist)/i.test(lower)) return true
  if (/not\s+found/.test(lower) && /session|chat|conversation/i.test(lower)) return true
  // Proxy sometimes returns only "Not Found" without the word session.
  if (/^not\s+found\.?$/i.test(msg.trim())) return true
  return false
}

/** User-facing title + description for chat errors. */
export function humanizeChatError(err: unknown): { title: string; description: string } {
  const raw =
    err instanceof Error
      ? err.message
      : typeof err === 'string'
        ? err
        : 'Something went wrong in chat'

  if (isOpenCodeSessionMissingError(err)) {
    return {
      title: 'Chat session not found in OpenCode',
      description:
        'This conversation is not registered on the harness (common after a browser refresh or sandbox recreate). Sync creates a new OpenCode session and keeps your visible history in Everflow.',
    }
  }

  const lower = raw.toLowerCase()
  if (/timeout|timed out|slow to accept/i.test(lower)) {
    return {
      title: 'OpenCode is slow to respond',
      description: raw,
    }
  }
  if (/http error talking to everflow api|everflow mcp|mcp/i.test(lower)) {
    return {
      title: 'Everflow tools could not reach the API',
      description: raw,
    }
  }
  if (/sandbox is not running|sandbox not found|missing on agent/i.test(lower)) {
    return {
      title: 'Sandbox is not available',
      description: raw,
    }
  }
  if (/harness|opencode ensure|catalog/i.test(lower)) {
    return {
      title: 'OpenCode harness problem',
      description: raw,
    }
  }

  // Avoid showing a bare "Not Found" as the only title.
  if (/^not\s+found\.?$/i.test(raw.trim())) {
    return {
      title: 'Chat request failed',
      description: 'The harness returned Not Found. Try Sync session or start a new chat.',
    }
  }

  return {
    title: 'Chat error',
    description: raw,
  }
}

/** Drop in-flight pending/local placeholders before migrating history. */
export function sanitizeMessagesForRemint(messages: ChatMessage[] | undefined): ChatMessage[] {
  if (!messages?.length) return []
  return messages.filter((m) => {
    if (!m?.id) return true
    if (m.id.startsWith('pending-')) return false
    if (m.id.startsWith('local-u-') && m.role === 'user') return true
    return m.generationStatus !== 'incomplete' || m.role === 'user'
  })
}

export type RemintResult = {
  session: OcSession
  conversation: ChatConversation
  oldSessionId?: string
}

/**
 * Create a new OpenCode session and build a conversation that carries local UI history.
 * Caller is responsible for writing projectChats / panel convId.
 * Uses dynamic imports so pure helpers stay loadable in selftests without Vite aliases.
 */
export async function remintOpenCodeSession(
  projectId: string,
  opts?: {
    oldSessionId?: string
    title?: string
    localMessages?: ChatMessage[]
    prev?: ChatConversation
  },
): Promise<RemintResult> {
  const { createSession, isOpenCodeSessionId } = await import('./client')
  const { sessionToConversation } = await import('./mapParts')
  const title = opts?.title || opts?.prev?.title || 'New chat'
  const session = await createSession(projectId, title)
  if (!isOpenCodeSessionId(session.id)) {
    throw new Error('OpenCode returned an invalid session id')
  }
  const messages = sanitizeMessagesForRemint(opts?.localMessages ?? opts?.prev?.messages)
  const conversation = sessionToConversation(session, messages)
  if (opts?.prev) {
    conversation.chatMode = opts.prev.chatMode
    conversation.primaryAgent = opts.prev.primaryAgent
    conversation.agents = opts.prev.agents
    conversation.metrics = opts.prev.metrics
    conversation.useWorktree = opts.prev.useWorktree
    conversation.worktree = opts.prev.worktree
    conversation.pinned = opts.prev.pinned
  }
  return {
    session,
    conversation,
    oldSessionId: opts?.oldSessionId,
  }
}

/** Replace old session id with reminted conversation in a chat list. */
export function replaceConversationInList(
  list: ChatConversation[],
  oldSessionId: string | undefined,
  next: ChatConversation,
): ChatConversation[] {
  if (!oldSessionId) {
    const withoutDup = list.filter((c) => c.id !== next.id)
    return [next, ...withoutDup]
  }
  const idx = list.findIndex((c) => c.id === oldSessionId)
  if (idx < 0) {
    const withoutDup = list.filter((c) => c.id !== next.id && c.id !== oldSessionId)
    return [next, ...withoutDup]
  }
  const copy = list.slice()
  copy[idx] = next
  // Drop any other ghost duplicates of the old id
  return copy.filter((c, i) => i === idx || c.id !== oldSessionId)
}
