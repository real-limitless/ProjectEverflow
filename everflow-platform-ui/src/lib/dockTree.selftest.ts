/**
 * Run: npx --yes tsx src/lib/dockTree.selftest.ts
 */
import type { LayoutNode } from '@/types/dock'
import {
  cloneLayout,
  findGroup,
  movePanelToGroupAt,
} from './dockTree'

let seq = 1
const nextId = () => `g${seq++}`

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

function tabsOf(layout: LayoutNode, groupId: string) {
  const g = findGroup(layout, groupId)
  assert(g, `group ${groupId} missing`)
  return g.node.tabs
}

// —— reorder within group ——
{
  seq = 1
  const layout: LayoutNode = {
    type: 'group',
    id: 'g1',
    tabs: ['preview:1', 'knowledge:1', 'code:1'],
    active: 'preview:1',
  }
  const next = movePanelToGroupAt(layout, 'g1', 'code:1', 0, nextId)
  assert(
    JSON.stringify(tabsOf(next, 'g1')) ===
      JSON.stringify(['code:1', 'preview:1', 'knowledge:1']),
    `reorder failed: ${tabsOf(next, 'g1')}`,
  )
  console.log('✓ reorder within group')
}

// —— move between groups, insert between tabs ——
{
  seq = 1
  const layout: LayoutNode = {
    type: 'split',
    direction: 'horizontal',
    sizes: [50, 50],
    children: [
      {
        type: 'group',
        id: 'g1',
        tabs: ['chat:1', 'terminal:1'],
        active: 'chat:1',
      },
      {
        type: 'group',
        id: 'g2',
        tabs: ['preview:1', 'knowledge:1', 'code:1'],
        active: 'preview:1',
      },
    ],
  }
  const next = movePanelToGroupAt(layout, 'g2', 'chat:1', 1, nextId)
  assert(
    JSON.stringify(tabsOf(next, 'g2')) ===
      JSON.stringify(['preview:1', 'chat:1', 'knowledge:1', 'code:1']),
    `cross insert failed: ${tabsOf(next, 'g2')}`,
  )
  assert(
    JSON.stringify(tabsOf(next, 'g1')) === JSON.stringify(['terminal:1']),
    `source should keep terminal: ${tabsOf(next, 'g1')}`,
  )
  console.log('✓ move between groups with insert index')
}

// —— cross-group insert at 0 and at end ——
{
  seq = 1
  const base: LayoutNode = {
    type: 'split',
    direction: 'horizontal',
    sizes: [50, 50],
    children: [
      { type: 'group', id: 'g1', tabs: ['chat:1'], active: 'chat:1' },
      {
        type: 'group',
        id: 'g2',
        tabs: ['preview:1', 'code:1'],
        active: 'preview:1',
      },
    ],
  }
  const atStart = movePanelToGroupAt(cloneLayout(base), 'g2', 'chat:1', 0, nextId)
  assert(
    JSON.stringify(tabsOf(atStart, 'g2')) ===
      JSON.stringify(['chat:1', 'preview:1', 'code:1']),
    `insert at 0 failed: ${tabsOf(atStart, 'g2')}`,
  )

  seq = 1
  const atEnd = movePanelToGroupAt(cloneLayout(base), 'g2', 'chat:1', 99, nextId)
  assert(
    JSON.stringify(tabsOf(atEnd, 'g2')) ===
      JSON.stringify(['preview:1', 'code:1', 'chat:1']),
    `insert at end failed: ${tabsOf(atEnd, 'g2')}`,
  )
  console.log('✓ cross-group insert at 0 and end')
}

// —— move last tab out prunes empty group / collapses split ——
{
  seq = 1
  const layout: LayoutNode = {
    type: 'split',
    direction: 'horizontal',
    sizes: [50, 50],
    children: [
      { type: 'group', id: 'g1', tabs: ['chat:1'], active: 'chat:1' },
      {
        type: 'group',
        id: 'g2',
        tabs: ['preview:1'],
        active: 'preview:1',
      },
    ],
  }
  const next = movePanelToGroupAt(layout, 'g2', 'chat:1', 0, nextId)
  // Must collapse to a single group (prune return assigned)
  assert(next.type === 'group', `expected collapsed group root, got ${next.type}`)
  assert(
    next.tabs.includes('chat:1') && next.tabs.includes('preview:1'),
    `collapsed group tabs wrong: ${next.tabs}`,
  )
  assert(
    JSON.stringify(next.tabs) === JSON.stringify(['chat:1', 'preview:1']) ||
      JSON.stringify(next.tabs) === JSON.stringify(['preview:1', 'chat:1']),
    `unexpected order: ${next.tabs}`,
  )
  // insert index 0 → chat first
  assert(
    JSON.stringify(next.tabs) === JSON.stringify(['chat:1', 'preview:1']),
    `insert at 0 after prune: ${next.tabs}`,
  )
  console.log('✓ prune empty group after last tab move (strict collapse)')
}

// clone isolation
{
  const layout: LayoutNode = {
    type: 'group',
    id: 'g1',
    tabs: ['a:1', 'b:1'],
    active: 'a:1',
  }
  const copy = cloneLayout(layout)
  copy.tabs.push('c:1')
  assert(layout.tabs.length === 2, 'clone mutated original')
  console.log('✓ clone isolation')
}

console.log('\nAll dockTree self-tests passed.')
