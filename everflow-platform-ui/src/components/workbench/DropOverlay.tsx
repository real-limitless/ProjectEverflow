import type { DropEdge } from '@/types/dock'

const ZONES: DropEdge[] = ['left', 'right', 'top', 'bottom', 'center']

interface DropOverlayProps {
  groupId: string
}

/**
 * Visual zones only — hit-testing is done by pointer-based dockTabDrag.
 * Shown while body has .is-panel-dragging / .is-dock-tab-dragging.
 */
export function DropOverlay({ groupId }: DropOverlayProps) {
  return (
    <div className="drop-overlay" aria-hidden>
      {ZONES.map((z) => (
        <div
          key={z}
          className={`drop-zone ${z}`}
          data-zone={z}
          data-group-id={groupId}
        >
          {z === 'center' ? 'Stack' : z}
        </div>
      ))}
    </div>
  )
}
