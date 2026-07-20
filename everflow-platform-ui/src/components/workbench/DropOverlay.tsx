import type { DropEdge } from '@/types/dock'
import { endPanelDrag, getDraggingPanelId } from '@/lib/panelDrag'
import { usePlaygroundStore } from '@/store/playgroundStore'

const ZONES: DropEdge[] = ['left', 'right', 'top', 'bottom', 'center']

interface DropOverlayProps {
  groupId: string
}

export function DropOverlay({ groupId }: DropOverlayProps) {
  const dropPanel = usePlaygroundStore((s) => s.dropPanel)

  return (
    <div className="drop-overlay">
      {ZONES.map((z) => (
        <div
          key={z}
          className={`drop-zone ${z}`}
          data-zone={z}
          data-group-id={groupId}
          onDragEnter={(e) => {
            e.preventDefault()
            e.currentTarget.classList.add('hot')
          }}
          onDragOver={(e) => {
            e.preventDefault()
            e.dataTransfer.dropEffect = 'move'
            e.currentTarget.classList.add('hot')
          }}
          onDragLeave={(e) => e.currentTarget.classList.remove('hot')}
          onDrop={(e) => {
            e.preventDefault()
            e.currentTarget.classList.remove('hot')
            const panelId =
              e.dataTransfer.getData('text/panel-id') || getDraggingPanelId()
            endPanelDrag()
            if (!panelId) return
            dropPanel(panelId, groupId, z)
          }}
        >
          {z === 'center' ? 'Stack' : z}
        </div>
      ))}
    </div>
  )
}
