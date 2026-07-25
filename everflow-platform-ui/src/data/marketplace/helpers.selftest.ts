/**
 * Lightweight self-test for marketplace filter/paginate helpers.
 * Run: npx tsx src/data/marketplace/helpers.selftest.ts
 */
import {
  filterMarketplaceItems,
  itemIconStyle,
  paginateItems,
  parseKindParam,
} from './helpers'
import type { MarketplaceItem } from './types'

const items: MarketplaceItem[] = [
  {
    id: 'a',
    kind: 'skill',
    name: 'Alpha Skill',
    description: 'does alpha things',
    origin: 'everflow',
    source: 'local',
    tags: ['alpha', 'core'],
  },
  {
    id: 'b',
    kind: 'skill',
    name: 'Beta Tool',
    description: 'ecc beta',
    origin: 'ecc',
    source: 'remote',
    tags: ['beta'],
  },
  {
    id: 'c',
    kind: 'skill',
    name: 'Gamma',
    description: 'curated gamma',
    origin: 'curated',
    source: 'x',
    tags: ['alpha'],
  },
]

function assert(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg)
}

const q = filterMarketplaceItems(items, { query: 'alpha' })
assert(q.length === 2, 'query alpha should match name/tag/desc')

const o = filterMarketplaceItems(items, { origin: 'ecc' })
assert(o.length === 1 && o[0].id === 'b', 'origin filter')

const t = filterMarketplaceItems(items, { tag: 'alpha' })
assert(t.length === 2, 'tag filter')

const page1 = paginateItems(items, 1, 2)
assert(page1.pageItems.length === 2 && page1.pageCount === 2, 'page 1 size 2')
const page2 = paginateItems(items, 2, 2)
assert(page2.pageItems.length === 1 && page2.page === 2, 'page 2')
const clamped = paginateItems(items, 99, 2)
assert(clamped.page === 2, 'clamp page')

assert(parseKindParam('skills') === 'skill', 'plural kind')
assert(parseKindParam('mcp') === 'mcp', 'mcp kind')
assert(parseKindParam('nope') === null, 'bad kind')

const icon = itemIconStyle('everflow-knowledge', 'Everflow Knowledge')
assert(icon.monogram.length === 2, 'monogram')
assert(icon.hue >= 0 && icon.hue < 360, 'hue range')

console.log('marketplace helpers.selftest: ok')
