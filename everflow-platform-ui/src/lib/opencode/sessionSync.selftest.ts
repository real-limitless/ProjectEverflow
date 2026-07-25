/**
 * Run: npx tsx src/lib/opencode/sessionSync.selftest.ts
 */
import {
  humanizeChatError,
  isOpenCodeSessionMissingError,
  replaceConversationInList,
  sanitizeMessagesForRemint,
} from './sessionSync'
import type { ChatConversation, ChatMessage } from '../../types/panels'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

// --- isOpenCodeSessionMissingError ---
assert(isOpenCodeSessionMissingError(new Error('Not Found')), 'bare Not Found')
assert(isOpenCodeSessionMissingError({ status: 404, message: 'x' }), 'status 404')
assert(isOpenCodeSessionMissingError(new Error('Session not found')), 'session not found')
assert(!isOpenCodeSessionMissingError(new Error('Internal Server Error')), '500 not missing')
assert(!isOpenCodeSessionMissingError(new Error('timeout')), 'timeout not missing')

// --- humanize ---
const h = humanizeChatError(new Error('Not Found'))
assert(
  h.title.toLowerCase().includes('session') || h.title.toLowerCase().includes('chat'),
  'title',
)
assert(h.description.length > 20, 'description explains sync')

// --- sanitize ---
const cleaned = sanitizeMessagesForRemint([
  { id: 'local-u-1', role: 'user', text: 'hi' },
  { id: 'pending-a-1', role: 'assistant', generationStatus: 'incomplete' },
  { id: 'a1', role: 'assistant', text: 'hello', generationStatus: 'complete' },
] as ChatMessage[])
assert(cleaned.length === 2, 'drops pending assistant')
assert(!cleaned.some((m) => m.id.startsWith('pending-')), 'no pending left')

// --- replace list ---
const list = [
  { id: 'ses_old', title: 'Old', messages: [] },
  { id: 'ses_other', title: 'Other', messages: [] },
] as unknown as ChatConversation[]
const next = {
  id: 'ses_new',
  title: 'Old',
  messages: [{ id: 'm1', role: 'user', text: 'hi' }],
} as unknown as ChatConversation
const replaced = replaceConversationInList(list, 'ses_old', next)
assert(replaced.some((c) => c.id === 'ses_new'), 'has new')
assert(!replaced.some((c) => c.id === 'ses_old'), 'old gone')
assert(replaced.some((c) => c.id === 'ses_other'), 'keeps other')

console.log('sessionSync.selftest: ok')
