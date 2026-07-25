/**
 * Run: npx tsx src/lib/knowledgeRag.selftest.ts
 * (format helper only — no network)
 */
import {
  formatKnowledgeHitsForPrompt,
  type KnowledgeHitLike,
} from './knowledgeRag'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

const hits: KnowledgeHitLike[] = [
  {
    canvas_name: 'Secrets',
    text: '## Knowledge key\nThe password is apple1234',
    score: 0.9,
  },
  {
    canvas_name: 'Noise',
    text: 'unrelated',
    score: 0.01,
  },
]

const block = formatKnowledgeHitsForPrompt(hits)
assert(block != null, 'formats high-score hits')
assert(block!.includes('apple1234'), 'includes secret chunk')
assert(block!.includes('vector index'), 'explains source')
assert(!block!.includes('unrelated'), 'drops low-score noise')

const empty = formatKnowledgeHitsForPrompt([])
assert(empty == null, 'empty → null')

console.log('knowledgeRag.selftest: ok')
