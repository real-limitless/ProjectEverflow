import { Button } from '@patternfly/react-core'
import type { GroupNode } from '@/types/dock'
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
        {node.active && node.tabs.includes(node.active) ? (
          <PanelHost panelKey={node.active} />
        ) : empty ? (
          <div className="empty-group">
            Drop a panel here
            <br />
            <span style={{ fontSize: 11, opacity: 0.7 }}>
              or use the Panels tray
            </span>
          </div>
        ) : (
          <div className="empty-group">Select a tab</div>
        )}
      </div>
      <DropOverlay groupId={node.id} />
    </div>
  )
}
