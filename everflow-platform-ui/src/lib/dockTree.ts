import type {
  DropEdge,
  GroupLocation,
  GroupNode,
  LayoutNode,
  PanelLocation,
  SplitNode,
} from '@/types/dock'
import type { PanelKey } from '@/types/panels'

export function cloneLayout<T>(node: T): T {
  return JSON.parse(JSON.stringify(node)) as T
}

export function findGroup(
  node: LayoutNode,
  groupId: string,
  parent: SplitNode | null = null,
  index = -1,
): GroupLocation | null {
  if (node.type === 'group' && node.id === groupId) {
    return { node, parent, index }
  }
  if (node.type === 'split') {
    for (let i = 0; i < node.children.length; i++) {
      const found = findGroup(node.children[i], groupId, node, i)
      if (found) return found
    }
  }
  return null
}

export function findPanelLocation(
  node: LayoutNode,
  panelId: PanelKey,
  parent: SplitNode | null = null,
  index = -1,
): PanelLocation | null {
  if (node.type === 'group') {
    const ti = node.tabs.indexOf(panelId)
    if (ti >= 0) return { group: node, parent, index, tabIndex: ti }
    return null
  }
  for (let i = 0; i < node.children.length; i++) {
    const found = findPanelLocation(node.children[i], panelId, node, i)
    if (found) return found
  }
  return null
}

export function allPanelsInLayout(node: LayoutNode, acc: PanelKey[] = []): PanelKey[] {
  if (node.type === 'group') {
    acc.push(...node.tabs)
  } else {
    node.children.forEach((c) => allPanelsInLayout(c, acc))
  }
  return acc
}

export function firstGroup(node: LayoutNode): GroupNode | null {
  if (node.type === 'group') return node
  for (const c of node.children) {
    const g = firstGroup(c)
    if (g) return g
  }
  return null
}

function replaceNode(
  root: LayoutNode,
  target: LayoutNode,
  replacement: LayoutNode,
): LayoutNode {
  if (root === target) return replacement
  if (root.type === 'split') {
    for (let i = 0; i < root.children.length; i++) {
      if (root.children[i] === target) {
        root.children[i] = replacement
        return root
      }
      const before = root.children[i]
      const after = replaceNode(before, target, replacement)
      if (after !== before) {
        root.children[i] = after
        return root
      }
    }
  }
  return root
}

function pruneEmptyGroup(
  layout: LayoutNode,
  parent: SplitNode | null,
  index: number,
  nextGroupId: () => string,
): LayoutNode {
  if (!parent) {
    if (layout.type === 'group' && layout.tabs.length === 0) {
      layout.active = null
    }
    return layout
  }

  parent.children.splice(index, 1)
  if (parent.children.length === 1) {
    const only = parent.children[0]
    return replaceNode(layout, parent, only)
  }
  if (parent.children.length === 0) {
    parent.children = [{ type: 'group', id: nextGroupId(), tabs: [], active: null }]
  } else {
    const n = parent.children.length
    parent.sizes = Array(n).fill(100 / n)
  }
  return layout
}

export function removePanelFromLayout(
  layout: LayoutNode,
  panelId: PanelKey,
  nextGroupId: () => string,
): LayoutNode {
  const root = cloneLayout(layout)
  const loc = findPanelLocation(root, panelId)
  if (!loc) return root

  const { group, parent, index } = loc
  group.tabs.splice(loc.tabIndex, 1)
  if (group.active === panelId) {
    group.active = group.tabs[Math.max(0, loc.tabIndex - 1)] || group.tabs[0] || null
  }
  if (group.tabs.length === 0) {
    return pruneEmptyGroup(root, parent, index, nextGroupId)
  }
  return root
}

export function addPanelToGroup(
  layout: LayoutNode,
  groupId: string,
  panelId: PanelKey,
  makeActive = true,
  nextGroupId: () => string,
): LayoutNode {
  let root = removePanelFromLayout(layout, panelId, nextGroupId)
  const found = findGroup(root, groupId)
  if (!found) {
    const first = firstGroup(root)
    if (first) {
      if (!first.tabs.includes(panelId)) first.tabs.push(panelId)
      if (makeActive) first.active = panelId
    }
    return root
  }
  if (!found.node.tabs.includes(panelId)) found.node.tabs.push(panelId)
  if (makeActive) found.node.active = panelId
  return root
}

export function splitGroup(
  layout: LayoutNode,
  groupId: string,
  panelId: PanelKey,
  edge: Exclude<DropEdge, 'center'>,
  nextGroupId: () => string,
): LayoutNode {
  let root = removePanelFromLayout(layout, panelId, nextGroupId)
  let found = findGroup(root, groupId)

  if (!found) {
    const fallback = firstGroup(root)
    if (fallback) {
      found = findGroup(root, fallback.id)
    }
  }

  if (!found) {
    if (root.type === 'group') {
      if (!root.tabs.includes(panelId)) root.tabs.push(panelId)
      root.active = panelId
    } else {
      root = {
        type: 'group',
        id: nextGroupId(),
        tabs: [panelId],
        active: panelId,
      }
    }
    return root
  }

  const existing = found.node
  if (existing.tabs.length === 0) {
    existing.tabs = [panelId]
    existing.active = panelId
    return root
  }

  const newGroup: GroupNode = {
    type: 'group',
    id: nextGroupId(),
    tabs: [panelId],
    active: panelId,
  }

  const direction = edge === 'left' || edge === 'right' ? 'horizontal' : 'vertical'
  const firstIsNew = edge === 'left' || edge === 'top'
  const splitNode: SplitNode = {
    type: 'split',
    direction,
    sizes: [50, 50],
    children: firstIsNew ? [newGroup, existing] : [existing, newGroup],
  }

  if (!found.parent) {
    return splitNode
  }
  found.parent.children[found.index] = splitNode
  return root
}

export function setActiveTab(
  layout: LayoutNode,
  groupId: string,
  panelId: PanelKey,
): LayoutNode {
  const root = cloneLayout(layout)
  const found = findGroup(root, groupId)
  if (found && found.node.tabs.includes(panelId)) {
    found.node.active = panelId
  }
  return root
}

export function addTabToGroup(
  layout: LayoutNode,
  groupId: string,
  panelId: PanelKey,
): LayoutNode {
  const root = cloneLayout(layout)
  const found = findGroup(root, groupId)
  if (!found) return root
  if (!found.node.tabs.includes(panelId)) {
    found.node.tabs.push(panelId)
  }
  found.node.active = panelId
  return root
}

export function updateSplitSizes(
  layout: LayoutNode,
  path: number[],
  sizes: number[],
): LayoutNode {
  const root = cloneLayout(layout)
  let node: LayoutNode = root
  for (const idx of path) {
    if (node.type !== 'split') return root
    node = node.children[idx]
  }
  // path points to the split itself when empty; when non-empty, last index is child
  // We pass path to the split node indices from root
  let target: LayoutNode = root
  if (path.length === 0) {
    if (target.type === 'split') target.sizes = sizes
    return root
  }
  // Re-walk: path is indices of children leading TO the split node
  target = root
  for (let i = 0; i < path.length; i++) {
    if (target.type !== 'split') return root
    if (i === path.length - 1 && path.length > 0) {
      // Actually for sash we need the split node containing the sash.
      // Simpler API: find by walking with path to split
    }
    target = target.children[path[i]]
  }
  return root
}

/** Update sizes on a split identified by a path of child indices from root to that split. */
export function setSizesAtPath(
  layout: LayoutNode,
  pathToSplit: number[],
  sizes: number[],
): LayoutNode {
  const root = cloneLayout(layout)
  if (pathToSplit.length === 0) {
    if (root.type === 'split') root.sizes = [...sizes]
    return root
  }
  let parent: LayoutNode = root
  for (let i = 0; i < pathToSplit.length - 1; i++) {
    if (parent.type !== 'split') return root
    parent = parent.children[pathToSplit[i]]
  }
  if (parent.type !== 'split') return root
  const child = parent.children[pathToSplit[pathToSplit.length - 1]]
  if (child?.type === 'split') {
    child.sizes = [...sizes]
  }
  return root
}

export function countTypeInLayout(type: string, node: LayoutNode): number {
  return allPanelsInLayout(node).filter((k) => {
    const i = String(k).indexOf(':')
    const t = i >= 0 ? k.slice(0, i) : k
    return t === type
  }).length
}
