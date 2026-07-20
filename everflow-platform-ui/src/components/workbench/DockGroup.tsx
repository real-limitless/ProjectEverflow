import { Button } from '@patternfly/react-core'
import type { GroupNode } from '@/types/dock'
import { beginPanelDrag, endPanelDrag } from '@/lib/panelDrag'
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

  const empty = node.tabs.length === 0

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
            return (
              <div
                key={pid}
                className={`panel-tab${active ? ' active' : ''}`}
                draggable
                title={panelTabLabel(pid)}
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest('[data-act]')) return
                  activateTab(node.id, pid)
                }}
                onDragStart={(e) => {
                  // Do NOT set React state here — re-render cancels HTML5 drag
                  beginPanelDrag(pid)
                  e.dataTransfer.setData('text/panel-id', pid)
                  e.dataTransfer.effectAllowed = 'move'
                  e.currentTarget.classList.add('dragging')
                }}
                onDragEnd={(e) => {
                  e.currentTarget.classList.remove('dragging')
                  endPanelDrag()
                }}
              >
                <span className="tab-icon">{meta.icon}</span>
                <span className="tab-label-text">{panelTabLabel(pid)}</span>
                <span className="tab-actions">
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
