/**
 * Pure geometry helpers for dock tab insert hit-testing.
 * No DOM APIs beyond rect shapes — unit-testable with plain objects.
 */

export type RectLike = {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

export type GroupTabGeometry = {
  groupId: string
  tabBar: RectLike
  tabRects: RectLike[]
}

export type BodyZoneGeometry = {
  groupId: string
  body: RectLike
}

export type TabInsertHit = { kind: 'tab-insert'; groupId: string; index: number }
export type ZoneHit = {
  kind: 'zone'
  groupId: string
  edge: 'left' | 'right' | 'top' | 'bottom' | 'center'
}
export type DockHit = TabInsertHit | ZoneHit

/** Insert index from tab midpoints (0 = before first, length = after last). */
export function insertIndexFromTabRects(
  tabRects: RectLike[],
  clientX: number,
): number {
  if (!tabRects.length) return 0
  for (let i = 0; i < tabRects.length; i++) {
    const r = tabRects[i]
    const mid = r.left + r.width / 2
    if (clientX < mid) return i
  }
  return tabRects.length
}

function expandRectY(r: RectLike, ySlack: number): RectLike {
  return {
    left: r.left,
    right: r.right,
    top: r.top - ySlack,
    bottom: r.bottom + ySlack,
    width: r.width,
    height: r.height + 2 * ySlack,
  }
}

function pointInRect(x: number, y: number, r: RectLike): boolean {
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
}

/**
 * If (x,y) is over any group's expanded tab bar, return tab-insert for that group.
 * Tab strip always wins over body zones.
 */
export function resolveTabInsertAtPoint(
  groups: GroupTabGeometry[],
  x: number,
  y: number,
  ySlack = 8,
): TabInsertHit | null {
  let best: { hit: TabInsertHit; dist: number } | null = null

  for (const g of groups) {
    const expanded = expandRectY(g.tabBar, ySlack)
    if (!pointInRect(x, y, expanded)) continue

    const index = insertIndexFromTabRects(g.tabRects, x)
    const midY = (g.tabBar.top + g.tabBar.bottom) / 2
    const dist = Math.abs(y - midY)
    const hit: TabInsertHit = { kind: 'tab-insert', groupId: g.groupId, index }
    if (!best || dist < best.dist) best = { hit, dist }
  }

  return best?.hit ?? null
}

/**
 * Resolve body zone from relative position inside a group body rect.
 * Uses same 22% band layout as DropOverlay CSS.
 */
export function resolveZoneAtPoint(
  bodies: BodyZoneGeometry[],
  x: number,
  y: number,
): ZoneHit | null {
  for (const b of bodies) {
    if (!pointInRect(x, y, b.body)) continue
    const w = b.body.width || 1
    const h = b.body.height || 1
    const rx = (x - b.body.left) / w
    const ry = (y - b.body.top) / h

    if (rx < 0.22) {
      return { kind: 'zone', groupId: b.groupId, edge: 'left' }
    }
    if (rx > 0.78) {
      return { kind: 'zone', groupId: b.groupId, edge: 'right' }
    }
    if (ry < 0.22) {
      return { kind: 'zone', groupId: b.groupId, edge: 'top' }
    }
    if (ry > 0.78) {
      return { kind: 'zone', groupId: b.groupId, edge: 'bottom' }
    }
    return { kind: 'zone', groupId: b.groupId, edge: 'center' }
  }
  return null
}

/** Full resolve: tab strip first, then body zones. */
export function resolveDockHit(
  groups: GroupTabGeometry[],
  bodies: BodyZoneGeometry[],
  x: number,
  y: number,
  ySlack = 8,
): DockHit | null {
  return (
    resolveTabInsertAtPoint(groups, x, y, ySlack) ??
    resolveZoneAtPoint(bodies, x, y)
  )
}
