import { useCallback, useRef, useState, type ReactNode } from 'react'
import { Button } from '@patternfly/react-core'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'

interface FloatingCoachPanelProps {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  defaultX?: number
  defaultY?: number
  width?: number
}

/** Draggable floating panel shell (agents coach, etc.). */
export function FloatingCoachPanel({
  title,
  open,
  onClose,
  children,
  footer,
  defaultX = 24,
  defaultY = 24,
  width = 320,
}: FloatingCoachPanelProps) {
  const [pos, setPos] = useState({ x: defaultX, y: defaultY })
  const drag = useRef<{ ox: number; oy: number; sx: number; sy: number } | null>(null)

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('button, input, textarea, a')) return
      drag.current = { ox: e.clientX, oy: e.clientY, sx: pos.x, sy: pos.y }
      ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    },
    [pos.x, pos.y],
  )

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag.current) return
    const dx = e.clientX - drag.current.ox
    const dy = e.clientY - drag.current.oy
    setPos({
      x: Math.max(8, drag.current.sx + dx),
      y: Math.max(8, drag.current.sy + dy),
    })
  }, [])

  const onPointerUp = useCallback(() => {
    drag.current = null
  }, [])

  if (!open) return null

  return (
    <div
      className="studio-floating-coach"
      style={{ left: pos.x, top: pos.y, width }}
      role="dialog"
      aria-label={title}
    >
      <div
        className="studio-floating-coach__header"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <span className="studio-floating-coach__title">{title}</span>
        <Button variant="plain" aria-label="Close coach" onClick={onClose} icon={<TimesIcon />} />
      </div>
      <div className="studio-floating-coach__body">{children}</div>
      {footer && <div className="studio-floating-coach__footer">{footer}</div>}
    </div>
  )
}
