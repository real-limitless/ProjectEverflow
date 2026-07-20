/**
 * Run: npx --yes tsx src/lib/dockTabHit.selftest.ts
 */
import {
  insertIndexFromTabRects,
  resolveDockHit,
  resolveTabInsertAtPoint,
  type BodyZoneGeometry,
  type GroupTabGeometry,
  type RectLike,
} from './dockTabHit'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

function rect(l: number, t: number, w: number, h: number): RectLike {
  return { left: l, top: t, right: l + w, bottom: t + h, width: w, height: h }
}

// Tabs: [0-100], [100-200], [200-300] at y 0-32
const tabs = [rect(0, 0, 100, 32), rect(100, 0, 100, 32), rect(200, 0, 100, 32)]

{
  assert(insertIndexFromTabRects(tabs, 10) === 0, 'left of first mid')
  assert(insertIndexFromTabRects(tabs, 60) === 1, 'right half of first → 1')
  assert(insertIndexFromTabRects(tabs, 150) === 2, 'right half of second → 2')
  assert(insertIndexFromTabRects(tabs, 290) === 3, 'past last → length')
  assert(insertIndexFromTabRects([], 50) === 0, 'empty → 0')
  console.log('✓ insertIndexFromTabRects')
}

const groups: GroupTabGeometry[] = [
  {
    groupId: 'gA',
    tabBar: rect(0, 0, 300, 32),
    tabRects: [rect(0, 0, 100, 32), rect(100, 0, 100, 32)],
  },
  {
    groupId: 'gB',
    tabBar: rect(400, 0, 400, 32),
    tabRects: [
      rect(400, 0, 100, 32), // preview
      rect(500, 0, 100, 32), // knowledge
      rect(600, 0, 100, 32), // code
    ],
  },
]

{
  // Between preview (400-500) and knowledge (500-600): x=520 is left half of knowledge → index 1
  const hit = resolveTabInsertAtPoint(groups, 520, 16)
  assert(hit?.groupId === 'gB' && hit.index === 1, `between tabs: ${JSON.stringify(hit)}`)
  console.log('✓ tab insert between two tabs in stack B')
}

{
  // y slightly below tab bar (y=36) still counts with slack 8 (bar bottom 32 + 8)
  const hit = resolveTabInsertAtPoint(groups, 520, 36, 8)
  assert(hit?.kind === 'tab-insert' && hit.groupId === 'gB', `y-slack: ${JSON.stringify(hit)}`)
  console.log('✓ expanded Y slack still tab-insert')
}

{
  // Body center of B — should NOT be tab-insert
  const bodies: BodyZoneGeometry[] = [
    { groupId: 'gB', body: rect(400, 32, 400, 300) },
  ]
  const tabOnly = resolveTabInsertAtPoint(groups, 600, 180, 8)
  assert(tabOnly === null, 'body center is not tab-insert')
  const full = resolveDockHit(groups, bodies, 600, 180, 8)
  assert(full?.kind === 'zone' && full.edge === 'center', `body center zone: ${JSON.stringify(full)}`)
  console.log('✓ body center → zone center, not tab-insert')
}

{
  // Over tab strip even if "zone would also cover" — tab wins
  const bodies: BodyZoneGeometry[] = [
    { groupId: 'gB', body: rect(400, 0, 400, 332) }, // includes tab y
  ]
  const full = resolveDockHit(groups, bodies, 520, 16, 8)
  assert(
    full?.kind === 'tab-insert' && full.index === 1,
    `tab beats zone: ${JSON.stringify(full)}`,
  )
  console.log('✓ tab strip beats body zone geometry')
}

{
  const bodies: BodyZoneGeometry[] = [
    { groupId: 'gB', body: rect(400, 32, 400, 300) },
  ]
  const left = resolveDockHit(groups, bodies, 420, 180)
  assert(left?.kind === 'zone' && left.edge === 'left', 'left zone')
  const right = resolveDockHit(groups, bodies, 780, 180)
  assert(right?.kind === 'zone' && right.edge === 'right', 'right zone')
  console.log('✓ edge zones')
}

console.log('\nAll dockTabHit self-tests passed.')
