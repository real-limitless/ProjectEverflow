/**
 * Pointer-based dock tab drag (not HTML5 DnD).
 * Supports: reorder within stack, insert between tabs in another stack,
 * body zones left/right/top/bottom/center for split/stack.
 *
 * Tab-strip geometry always wins over body zones (see dockTabHit.ts).
 */

import type { DropEdge } from '@/types/dock'
import {
  resolveDockHit,
  type BodyZoneGeometry,
  type DockHit,
  type GroupTabGeometry,
  type RectLike,
} from '@/lib/dockTabHit'

export type DockTabDropTarget =
  | { kind: 'tab-insert'; groupId: string; index: number }
  | { kind: 'zone'; groupId: string; edge: DropEdge }

type Session = {
  panelId: string
  pointerId: number
  startX: number
  startY: number
  active: boolean
  ghost: HTMLElement
  caret: HTMLElement
  lastTarget: DockTabDropTarget | null
  sourceEl: HTMLElement | null
  prevUserSelect: string
  cleanup: (() => void) | null
}

let session: Session | null = null

const Y_SLACK = 8

function ensureUi(): { ghost: HTMLElement; caret: HTMLElement } {
  let ghost = document.getElementById('dock-tab-ghost') as HTMLElement | null
  if (!ghost) {
    ghost = document.createElement('div')
    ghost.id = 'dock-tab-ghost'
    ghost.className = 'dock-tab-ghost'
    document.body.appendChild(ghost)
  }
  let caret = document.getElementById('dock-tab-caret') as HTMLElement | null
  if (!caret) {
    caret = document.createElement('div')
    caret.id = 'dock-tab-caret'
    caret.className = 'dock-tab-caret'
    document.body.appendChild(caret)
  }
  return { ghost, caret }
}

function clearHighlights(): void {
  document
    .querySelectorAll('.tab-bar.is-tab-drop-target, .drop-zone.hot, .dock-group.drop-target')
    .forEach((el) => {
      el.classList.remove('is-tab-drop-target', 'hot', 'drop-target')
    })
}

function hideUi(s: Session): void {
  s.ghost.style.display = 'none'
  s.caret.style.display = 'none'
  clearHighlights()
  s.sourceEl?.classList.remove('dragging')
  document.body.classList.remove('is-dock-tab-dragging')
  document.body.style.userSelect = s.prevUserSelect
}

function rectFromEl(el: Element): RectLike {
  const r = el.getBoundingClientRect()
  return {
    left: r.left,
    top: r.top,
    right: r.right,
    bottom: r.bottom,
    width: r.width,
    height: r.height,
  }
}

function collectGeometry(): {
  groups: GroupTabGeometry[]
  bodies: BodyZoneGeometry[]
} {
  const groups: GroupTabGeometry[] = []
  const bodies: BodyZoneGeometry[] = []

  document.querySelectorAll<HTMLElement>('.dock-group[data-group-id]').forEach((groupEl) => {
    const groupId = groupEl.dataset.groupId
    if (!groupId) return

    const tabBar = groupEl.querySelector('.tab-bar')
    if (tabBar) {
      const tabsEl = tabBar.querySelector('.tab-bar-tabs')
      const tabRects = tabsEl
        ? Array.from(tabsEl.querySelectorAll('[data-panel-tab]')).map(rectFromEl)
        : []
      groups.push({
        groupId,
        tabBar: rectFromEl(tabBar),
        tabRects,
      })
    }

    const body = groupEl.querySelector('.panel-body')
    if (body) {
      bodies.push({ groupId, body: rectFromEl(body) })
    } else {
      // Fallback: group rect below tab bar
      const gr = groupEl.getBoundingClientRect()
      const barH = tabBar?.getBoundingClientRect().height ?? 32
      bodies.push({
        groupId,
        body: {
          left: gr.left,
          top: gr.top + barH,
          right: gr.right,
          bottom: gr.bottom,
          width: gr.width,
          height: Math.max(0, gr.height - barH),
        },
      })
    }
  })

  return { groups, bodies }
}

function hitTest(x: number, y: number): DockTabDropTarget | null {
  const s = session
  if (s) s.ghost.style.visibility = 'hidden'
  const { groups, bodies } = collectGeometry()
  if (s) s.ghost.style.visibility = 'visible'

  const hit: DockHit | null = resolveDockHit(groups, bodies, x, y, Y_SLACK)
  return hit
}

function placeCaretAtTab(tabEl: HTMLElement, before: boolean): void {
  const s = session
  if (!s) return
  const r = tabEl.getBoundingClientRect()
  const x = before ? r.left : r.right
  s.caret.style.display = 'block'
  s.caret.style.left = `${x - 1.5}px`
  s.caret.style.top = `${r.top + 4}px`
  s.caret.style.height = `${Math.max(16, r.height - 8)}px`
  tabEl.closest('.tab-bar')?.classList.add('is-tab-drop-target')
}

function placeCaretAtBarEnd(barTabs: HTMLElement): void {
  const s = session
  if (!s) return
  const r = barTabs.getBoundingClientRect()
  const last = barTabs.querySelector('.panel-tab-slot:last-child, .panel-tab:last-child')
  if (last) {
    const lr = last.getBoundingClientRect()
    s.caret.style.display = 'block'
    s.caret.style.left = `${lr.right - 1.5}px`
    s.caret.style.top = `${lr.top + 4}px`
    s.caret.style.height = `${Math.max(16, lr.height - 8)}px`
  } else {
    s.caret.style.display = 'block'
    s.caret.style.left = `${r.left + 4}px`
    s.caret.style.top = `${r.top + 4}px`
    s.caret.style.height = `${Math.max(16, r.height - 8)}px`
  }
  barTabs.closest('.tab-bar')?.classList.add('is-tab-drop-target')
}

function paintTarget(target: DockTabDropTarget | null): void {
  clearHighlights()
  const s = session
  if (!s) return
  if (!target) {
    s.caret.style.display = 'none'
    return
  }

  if (target.kind === 'tab-insert') {
    const group = document.querySelector(
      `.dock-group[data-group-id="${CSS.escape(target.groupId)}"]`,
    ) as HTMLElement | null
    const tabsEl = group?.querySelector('.tab-bar-tabs') as HTMLElement | null
    if (!tabsEl) {
      s.caret.style.display = 'none'
      return
    }
    const tabs = Array.from(
      tabsEl.querySelectorAll<HTMLElement>('[data-panel-tab]'),
    )
    if (target.index >= tabs.length) {
      placeCaretAtBarEnd(tabsEl)
    } else if (tabs[target.index]) {
      placeCaretAtTab(tabs[target.index], true)
    } else {
      placeCaretAtBarEnd(tabsEl)
    }
    return
  }

  // zone — paint visual only
  s.caret.style.display = 'none'
  const group = document.querySelector(
    `.dock-group[data-group-id="${CSS.escape(target.groupId)}"]`,
  )
  group?.classList.add('drop-target')
  const zone = group?.querySelector(
    `.drop-zone.${CSS.escape(target.edge)}`,
  ) as HTMLElement | null
  zone?.classList.add('hot')
}

export function isDockTabDragging(): boolean {
  return !!session?.active
}

export function startDockTabDrag(opts: {
  panelId: string
  label: string
  event: PointerEvent
  sourceEl?: HTMLElement | null
  onComplete: (target: DockTabDropTarget | null, panelId: string) => void
}): void {
  if (session) endDockTabDrag()

  const { ghost, caret } = ensureUi()
  ghost.textContent = opts.label
  ghost.style.display = 'block'
  ghost.style.left = `${opts.event.clientX + 12}px`
  ghost.style.top = `${opts.event.clientY + 8}px`
  caret.style.display = 'none'

  const sourceEl =
    opts.sourceEl ??
    (opts.event.currentTarget instanceof HTMLElement
      ? opts.event.currentTarget
      : null)

  session = {
    panelId: opts.panelId,
    pointerId: opts.event.pointerId,
    startX: opts.event.clientX,
    startY: opts.event.clientY,
    active: false,
    ghost,
    caret,
    lastTarget: null,
    sourceEl,
    prevUserSelect: document.body.style.userSelect,
    cleanup: null,
  }

  const onMove = (e: PointerEvent) => {
    if (!session || e.pointerId !== session.pointerId) return
    const dx = e.clientX - session.startX
    const dy = e.clientY - session.startY
    if (!session.active) {
      if (Math.hypot(dx, dy) < 5) return
      session.active = true
      // Only tab-drag class — do NOT arm is-panel-dragging zone pointer-events
      document.body.classList.add('is-dock-tab-dragging')
      document.body.style.userSelect = 'none'
      session.sourceEl?.classList.add('dragging')
    }
    session.ghost.style.left = `${e.clientX + 12}px`
    session.ghost.style.top = `${e.clientY + 8}px`
    const target = hitTest(e.clientX, e.clientY)
    session.lastTarget = target
    paintTarget(target)
  }

  const onUp = (e: PointerEvent) => {
    if (!session || e.pointerId !== session.pointerId) return
    const s = session
    const panelId = s.panelId
    // Re-hit-test at release point
    const target = s.active ? hitTest(e.clientX, e.clientY) : null
    const finish = s.cleanup
    if (finish) finish()
    else {
      hideUi(s)
      session = null
    }
    opts.onComplete(target, panelId)
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Escape') return
    const finish = session?.cleanup
    if (finish) finish()
    opts.onComplete(null, opts.panelId)
  }

  const cleanup = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    window.removeEventListener('keydown', onKey)
    if (session) hideUi(session)
    session = null
  }

  session.cleanup = cleanup

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
  window.addEventListener('keydown', onKey)
}

export function endDockTabDrag(): void {
  if (!session) return
  if (session.cleanup) session.cleanup()
  else {
    hideUi(session)
    session = null
  }
}
