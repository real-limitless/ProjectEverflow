/**
 * Run: npx tsx src/lib/projectCatalogSync.selftest.ts
 */
import {
  filterOpenIdsAfterPurge,
  resolveCurrentAfterPurge,
  selectStaleProjectIds,
} from './projectCatalogSync'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

const seeds = new Set(['aura', 'callour', 'router'])

// Demo mode never prunes
assert(
  selectStaleProjectIds(
    [{ id: 'ghost', fromApi: true }],
    [],
    { demoMode: true, seedIds: seeds },
  ).length === 0,
  'demo mode keeps ghosts',
)

// Pure seeds kept even when not in API
assert(
  selectStaleProjectIds(
    [
      { id: 'aura' },
      { id: 'callour', fromApi: false },
    ],
    [],
    { seedIds: seeds },
  ).length === 0,
  'pure seeds not stale',
)

// API-backed ghost (deleted project / wiped DB) is stale
const stale1 = selectStaleProjectIds(
  [
    { id: 'aura' },
    { id: 'uuid-alive', fromApi: true },
    { id: 'uuid-dead', fromApi: true },
    { id: 'local-orphan', fromApi: false },
  ],
  ['uuid-alive'],
  { seedIds: seeds },
)
assert(stale1.includes('uuid-dead'), 'missing API id is stale')
assert(stale1.includes('local-orphan'), 'local orphan non-seed is stale')
assert(!stale1.includes('uuid-alive'), 'live API id kept')
assert(!stale1.includes('aura'), 'seed kept')

// Empty API list purges all non-seed
const staleEmpty = selectStaleProjectIds(
  [
    { id: 'a', fromApi: true },
    { id: 'b', fromApi: true },
    { id: 'aura' },
  ],
  [],
  { seedIds: seeds },
)
assert(staleEmpty.sort().join(',') === 'a,b', 'empty API purges non-seeds only')

// Seed marked fromApi but missing from API → stale
assert(
  selectStaleProjectIds([{ id: 'aura', fromApi: true }], [], { seedIds: seeds }).includes(
    'aura',
  ),
  'seed fromApi missing is stale',
)

// Open tabs after purge
const open = filterOpenIdsAfterPurge(
  ['alive', 'dead', 'missing'],
  ['dead'],
  (id) => id === 'alive' || id === 'dead',
)
assert(open.join(',') === 'alive', 'open filter drops removed and missing catalog')

assert(resolveCurrentAfterPurge('dead', ['alive', 'other']) === 'alive', 'current falls back')
assert(resolveCurrentAfterPurge('alive', ['alive', 'other']) === 'alive', 'current kept')
assert(resolveCurrentAfterPurge('x', []) === null, 'no open → null current')

console.log('projectCatalogSync.selftest: ok')
