/**
 * Client-side helpers to inject project knowledge into OpenCode prompts.
 * Platform stores chunk embeddings; Chat retrieves before prompt_async.
 */

/** Min score to include a hit in auto-injected context (0–1). */
export const KNOWLEDGE_AUTO_INJECT_MIN_SCORE = 0.12

export type KnowledgeHitLike = {
  canvas_name?: string | null
  text?: string | null
  score?: number | null
}

export function formatKnowledgeHitsForPrompt(
  hits: KnowledgeHitLike[],
  opts?: { minScore?: number; maxHits?: number },
): string | null {
  const minScore = opts?.minScore ?? KNOWLEDGE_AUTO_INJECT_MIN_SCORE
  const maxHits = opts?.maxHits ?? 6
  const usable = hits
    .filter((h) => (h.score ?? 0) >= minScore && (h.text || '').trim())
    .slice(0, maxHits)
  if (!usable.length) return null
  const blocks = usable.map((h, i) => {
    const name = h.canvas_name || 'canvas'
    const score = typeof h.score === 'number' ? h.score.toFixed(3) : '?'
    return `### [${i + 1}] ${name} (score=${score})\n${(h.text || '').trim()}`
  })
  return (
    '## Project knowledge (auto-retrieved from Everflow vector index)\n\n' +
    'Use the following cite-backed chunks when answering. Prefer this over claiming ' +
    'you lack access to passwords/keys/docs. Everflow knowledge is not MCP "resources" — ' +
    'it is this index (and the everflow MCP knowledge_search tool).\n\n' +
    blocks.join('\n\n')
  )
}

/**
 * Retrieve top chunks for a user query. Returns null on empty/errors (non-fatal).
 */
export async function buildKnowledgeSystemContext(
  projectId: string,
  query: string,
  opts?: { topK?: number; minScore?: number },
): Promise<string | null> {
  const q = (query || '').trim()
  if (!q || !projectId) return null
  try {
    const { retrieveKnowledge } = await import('./api')
    const res = await retrieveKnowledge(projectId, {
      query: q,
      top_k: opts?.topK ?? 6,
    })
    return formatKnowledgeHitsForPrompt(res.hits || [], {
      minScore: opts?.minScore ?? KNOWLEDGE_AUTO_INJECT_MIN_SCORE,
    })
  } catch {
    return null
  }
}
