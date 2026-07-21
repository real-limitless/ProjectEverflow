import { useEffect, useMemo, useState } from 'react'
import { Button } from '@patternfly/react-core'
import type { GroupNode } from '@/types/dock'
import type { PanelKey } from '@/types/panels'
import {
  startDockTabDrag,
  type DockTabDropTarget,
} from '@/lib/dockTabDrag'
import { panelMetaOf } from '@/lib/panelIds'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { DropOverlay } from './DropOverlay'
import { PanelHost } from './PanelHost'

interface DockGroupProps {
  node: GroupNode
}

/**
 * Lazy-mount + keep-alive: once a tab is activated it stays mounted (hidden)
 * until closed or removed from the group. Prevents Terminal PTY WebSockets from
 * being torn down when the user switches dock tabs.
 */
export function DockGroup({ node }: DockGroupProps) {
  const activateTab = usePlaygroundStore((s) => s.activateTab)
  const closePanel = usePlaygroundStore((s) => s.closePanel)
  const duplicatePanel = usePlaygroundStore((s) => s.duplicatePanel)
  const detachPanel = usePlaygroundStore((s) => s.detachPanel)
  const panelTabLabel = usePlaygroundStore((s) => s.panelTabLabel)
  const setPaletteVisible = usePlaygroundStore((s) => s.setPaletteVisible)
  const movePanelToGroup = usePlaygroundStore((s) => s.movePanelToGroup)
  const dropPanel = usePlaygroundStore((s) => s.dropPanel)

  const empty = node.tabs.length === 0

  const [visited, setVisited] = useState<Set<PanelKey>>(() => {
    const initial = new Set<PanelKey>()
    if (node.active && node.tabs.includes(node.active)) initial.add(node.active)
    return initial
  })

  // Mark active tab as visited (first open mounts; later switches keep-alive).
  useEffect(() => {
    if (!node.active || !node.tabs.includes(node.active)) return
    const active = node.active
    setVisited((prev) => {
      if (prev.has(active)) return prev
      const next = new Set(prev)
      next.add(active)
      return next
    })
  }, [node.active, node.tabs])

  // Drop keep-alive for tabs no longer in this group (closed / moved away).
  useEffect(() => {
    const tabSet = new Set(node.tabs)
    setVisited((prev) => {
      let changed = false
      const next = new Set<PanelKey>()
      for (const pid of prev) {
        if (tabSet.has(pid)) next.add(pid)
        else changed = true
      }
      return changed ? next : prev
    })
  }, [node.tabs])

  // After a keep-alive pane becomes visible, force layout consumers (xterm FitAddon,
  // editors) to remeasure — size was 0×0 while display:none.
  useEffect(() => {
    if (!node.active) return
    const id = window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'))
    })
    return () => window.cancelAnimationFrame(id)
  }, [node.active])

  // Mount order: preserve visit order for stability; only tabs still in group.
  const mountedTabs = useMemo(() => {
    const tabSet = new Set(node.tabs)
    const ordered: PanelKey[] = []
    for (const pid of visited) {
      if (tabSet.has(pid)) ordered.push(pid)
    }
    // Active may not be in visited yet for one render frame — ensure it mounts.
    if (node.active && tabSet.has(node.active) && !ordered.includes(node.active)) {
      ordered.push(node.active)
    }
    return ordered
  }, [visited, node.tabs, node.active])

  const applyDrop = (target: DockTabDropTarget | null, panelId: string) => {
    if (!target) return
    if (target.kind === 'tab-insert') {
      movePanelToGroup(panelId, target.groupId, target.index)
      return
    }
    // body zone
    dropPanel(panelId, target.groupId, target.edge)
  }

  return (
    <div
      className={`dock-group${empty ? ' empty-drop' : ''}`}
      data-group-id={node.id}
    >
      <div className="tab-bar">
        <div className="tab-bar-tabs">
          {node.tabs.map((pid) => {
            const meta = panelMetaOf(pid)
            if (!meta) return null
            const active = node.active === pid
            const label = panelTabLabel(pid)
            return (
              <div key={pid} className="panel-tab-slot">
                <div
                  className={`panel-tab${active ? ' active' : ''}`}
                  data-panel-tab={pid}
                  title={label}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('[data-act]')) return
                    activateTab(node.id, pid)
                  }}
                  onPointerDown={(e) => {
                    if (e.button !== 0) return
                    if ((e.target as HTMLElement).closest('[data-act]')) return
                    // Window listeners + geometry hit-test (no element capture)
                    startDockTabDrag({
                      panelId: pid,
                      label,
                      event: e.nativeEvent,
                      sourceEl: e.currentTarget,
                      onComplete: applyDrop,
                    })
                  }}
                >
                  <span className="tab-icon">{meta.icon}</span>
                  <span className="tab-label-text">{label}</span>
                  <span
                    className="tab-actions"
                    onPointerDown={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      data-act="dup"
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
        {empty ? (
          <div className="empty-group">
            Drop a panel here
            <br />
            <span style={{ fontSize: 11, opacity: 0.7 }}>
              or use the Panels tray
            </span>
          </div>
        ) : mountedTabs.length === 0 ? (
          <div className="empty-group">Select a tab</div>
        ) : (
          mountedTabs.map((pid) => {
            const isActive = pid === node.active
            return (
              <div
                key={pid}
                className={`panel-body-pane${isActive ? ' is-active' : ''}`}
                hidden={!isActive}
                data-panel-pane={pid}
              >
                <PanelHost panelKey={pid} />
              </div>
            )
          })
        )}
      </div>
      <DropOverlay groupId={node.id} />
    </div>
  )
}
