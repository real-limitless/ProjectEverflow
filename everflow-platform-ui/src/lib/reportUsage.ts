/**
 * Fire-and-forget AI usage ingest from completed OpenCode chat turns.
 * Dedupes by message id in-memory for the tab lifetime.
 */

import {
  isDemoMode,
  reportUsageEventsBatch,
  type AiUsageEventPayload,
} from '@/lib/api'
import { assistantTurnReady } from '@/lib/opencode/mapParts'
import type { ChatMessage } from '@/types/panels'

const reportedIds = new Set<string>()

function hasTokenSignal(m: ChatMessage): boolean {
  const met = m.metrics
  if (!met) return false
  return (
    (met.inputTokens ?? 0) > 0 ||
    (met.outputTokens ?? 0) > 0 ||
    (met.completionTokens ?? 0) > 0 ||
    (met.contextUsedTokens ?? 0) > 0 ||
    (met.reasoningTokens ?? 0) > 0 ||
    (met.cacheReadTokens ?? 0) > 0 ||
    (met.cacheWriteTokens ?? 0) > 0
  )
}

export function usagePayloadFromMessage(
  sessionId: string,
  message: ChatMessage,
): AiUsageEventPayload | null {
  if (!message.id || message.role !== 'assistant') return null
  if (message.id.startsWith('pending-')) return null
  if (!assistantTurnReady(message) && !hasTokenSignal(message)) return null
  if (!hasTokenSignal(message) && message.generationStatus !== 'complete') {
    return null
  }

  const met = message.metrics
  const input = met?.inputTokens ?? 0
  const output = met?.outputTokens ?? met?.completionTokens ?? 0
  const reasoning = met?.reasoningTokens ?? 0
  const cacheRead = met?.cacheReadTokens ?? 0
  const cacheWrite = met?.cacheWriteTokens ?? 0
  const total =
    met?.contextUsedTokens ??
    input + output + reasoning + cacheRead

  return {
    session_id: sessionId,
    message_id: message.id,
    provider: met?.provider ?? null,
    model: met?.model ?? null,
    input_tokens: input,
    output_tokens: output,
    reasoning_tokens: reasoning,
    cache_read_tokens: cacheRead,
    cache_write_tokens: cacheWrite,
    total_tokens: total > 0 ? total : input + output + reasoning + cacheRead,
    duration_ms: met?.durationMs ?? null,
    ttft_ms: met?.ttftMs ?? null,
    occurred_at: message.createdAt ?? new Date().toISOString(),
    completed: message.generationStatus === 'complete' || assistantTurnReady(message),
  }
}

/** Report all reportable assistant turns in a session (backfill + live). */
export function reportUsageFromMessages(
  projectId: string | undefined | null,
  sessionId: string | undefined | null,
  messages: ChatMessage[],
): void {
  if (!projectId || !sessionId || isDemoMode()) return
  if (!messages.length) return

  const events: AiUsageEventPayload[] = []
  for (const m of messages) {
    if (reportedIds.has(m.id)) continue
    const payload = usagePayloadFromMessage(sessionId, m)
    if (!payload) continue
    // Skip pure zero unless completed with no tokens (still skip — no value).
    const sum =
      (payload.input_tokens ?? 0) +
      (payload.output_tokens ?? 0) +
      (payload.reasoning_tokens ?? 0) +
      (payload.cache_read_tokens ?? 0) +
      (payload.cache_write_tokens ?? 0)
    if (sum <= 0 && (payload.total_tokens ?? 0) <= 0) continue
    reportedIds.add(m.id)
    events.push(payload)
  }
  if (!events.length) return

  void reportUsageEventsBatch(projectId, events).catch(() => {
    // Allow retry on next hydrate if ingest failed.
    for (const e of events) reportedIds.delete(e.message_id)
  })
}
