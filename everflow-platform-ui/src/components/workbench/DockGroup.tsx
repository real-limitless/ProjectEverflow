import { useState, type DragEvent } from 'react'
import { Button } from '@patternfly/react-core'
import type { GroupNode } from '@/types/dock'
import {
  beginPanelDrag,
  endPanelDrag,
  getDraggingPanelId,
  markPanelDraggingUi,
} from '@/lib/panelDrag'
import { panelMetaOf } from '@/lib/panelIds'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { DropOverlay } from './DropOverlay'
import { PanelHost } from './PanelHost'

interface DockGroupProps {
  node: GroupNode
}

/** Compute insert index from mouse X relative to tab elements. */
function insertIndexFromPoint(
  tabsEl: HTMLElement,
  clientX: number,
  tabCount: number,
): number {
  const tabs = Array.from(
    tabsEl.querySelectorAll<HTMLElement>('[data-panel-tab]'),
  )
  if (!tabs.length) return tabCount
  for (let i = 0; i < tabs.length; i++) {
    const r = tabs[i].getBoundingClientRect()
    const mid = r.left + r.width / 2
    if (clientX < mid) return i
  }
  return tabs.length
}

export function DockGroup({ node }: DockGroupProps) {
  const activateTab = usePlaygroundStore((s) => s.activateTab)
  const closePanel = usePlaygroundStore((s) => s.closePanel)
  const duplicatePanel = usePlaygroundStore((s) => s.duplicatePanel)
  const detachPanel = usePlaygroundStore((s) => s.detachPanel)
  const panelTabLabel = usePlaygroundStore((s) => s.panelTabLabel)
  const setPaletteVisible = usePlaygroundStore((s) => s.setPaletteVisible)
  const movePanelToGroup = usePlaygroundStore((s) => s.movePanelToGroup)

  const empty = node.tabs.length === 0
  const [insertIndex, setInsertIndex] = useState<number | null>(null)

  const onTabBarDragOver = (e: DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    const tabsEl = e.currentTarget.querySelector(
      '.tab-bar-tabs',
    ) as HTMLElement | null
    if (!tabsEl) return
    const idx = insertIndexFromPoint(tabsEl, e.clientX, node.tabs.length)
    setInsertIndex(idx)
  }

  const onTabBarDrop = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const panelId =
      e.dataTransfer.getData('text/panel-id') ||
      e.dataTransfer.getData('text/plain') ||
      getDraggingPanelId()
    const tabsEl = e.currentTarget.querySelector(
      '.tab-bar-tabs',
    ) as HTMLElement | null
    const idx = tabsEl
      ? insertIndexFromPoint(tabsEl, e.clientX, node.tabs.length)
      : node.tabs.length
    setInsertIndex(null)
    endPanelDrag()
    if (!panelId) return
    movePanelToGroup(panelId, node.id, idx)
  }

  const onTabBarDragLeave = (e: DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setInsertIndex(null)
    }
  }

  return (
    <div
      className={`dock-group${empty ? ' empty-drop' : ''}`}
      data-group-id={node.id}
    >
      <div
        className={`tab-bar${insertIndex != null ? ' is-tab-drop-target' : ''}`}
        onDragOver={onTabBarDragOver}
        onDrop={onTabBarDrop}
        onDragLeave={onTabBarDragLeave}
      >
        <div className="tab-bar-tabs">
          {node.tabs.map((pid, i) => {
            const meta = panelMetaOf(pid)
            if (!meta) return null
            const active = node.active === pid
            return (
              <div key={pid} className="panel-tab-slot">
                {insertIndex === i ? (
                  <div className="tab-insert-indicator" aria-hidden />
                ) : null}
                <div
                  className={`panel-tab${active ? ' active' : ''}`}
                  data-panel-tab={pid}
                  draggable
                  title={panelTabLabel(pid)}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('[data-act]')) return
                    activateTab(node.id, pid)
                  }}
                  onDragStart={(e) => {
                    if ((e.target as HTMLElement).closest('[data-act]')) {
                      e.preventDefault()
                      return
                    }
                    beginPanelDrag(pid)
                    e.dataTransfer.setData('text/panel-id', pid)
                    e.dataTransfer.setData('text/plain', pid)
                    e.dataTransfer.effectAllowed = 'move'
                    e.currentTarget.classList.add('dragging')
                    requestAnimationFrame(() => markPanelDraggingUi())
                  }}
                  onDragEnd={(e) => {
                    e.currentTarget.classList.remove('dragging')
                    setInsertIndex(null)
                    endPanelDrag()
                  }}
                >
                  <span className="tab-icon" draggable={false}>
                    {meta.icon}
                  </span>
                  <span className="tab-label-text" draggable={false}>
                    {panelTabLabel(pid)}
                  </span>
                  <span
                    className="tab-actions"
                    draggable={false}
                    onMouseDown={(e) => e.stopPropagation()}
                    onDragStart={(e) => e.preventDefault()}
                  >
                    <button
                      type="button"
                      data-act="dup"
                      draggable={false}
                      title={`Open another ${meta.label}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        duplicatePanel(node.id, pid)
                      }}
                    >
                      +
                    </button>
                    <button
                      type="button"
                      data-act="detach"
                      draggable={false}
                      title="Detach to window"
                      onClick={(e) => {
                        e.stopPropagation()
                        detachPanel(pid)
                      }}
                    >
                      ↗
                    </button>
                    <button
                      type="button"
                      data-act="close"
                      draggable={false}
                      title="Close panel (reopen from Panels tray)"
                      onClick={(e) => {
                        e.stopPropagation()
                        closePanel(pid)
                        setPaletteVisible(true)
                      }}
                    >
                      ×
                    </button>
                  </span>
                </div>
              </div>
            )
          })}
          {insertIndex === node.tabs.length ? (
            <div className="tab-insert-indicator" aria-hidden />
          ) : null}
        </div>
        <div className="tab-bar-tools">
          {node.tabs.length && node.active ? (
            <Button
              variant="plain"
              size="sm"
              title="Detach active panel"
              onClick={() => node.active && detachPanel(node.active)}
            >
              ↗
            </Button>
          ) : null}
        </div>
      </div>
      <div className="panel-body">
        {node.active && node.tabs.includes(node.active) ? (
          <PanelHost panelKey={node.active} />
        ) : empty ? (
          <div className="empty-group">
            Drop a panel here
            <br />
            <span style={{ fontSize: 11, opacity: 0.7 }}>or use the Panels tray</span>
          </div>
        ) : (
          <div className="empty-group">Select a tab</div>
        )}
      </div>
      <DropOverlay groupId={node.id} />
    </div>
  )
}
