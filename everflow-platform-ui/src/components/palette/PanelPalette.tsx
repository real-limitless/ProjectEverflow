import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { PANEL_META } from '@/data/panelMeta'
import { PANEL_TYPES } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function PanelPalette() {
  const mode = usePlaygroundStore((s) => s.paletteMode)
  const pos = usePlaygroundStore((s) => s.palettePos)
  const visible = usePlaygroundStore((s) => s.paletteVisible)
  const setPaletteMode = usePlaygroundStore((s) => s.setPaletteMode)
  const setPalettePos = usePlaygroundStore((s) => s.setPalettePos)
  const setPaletteVisible = usePlaygroundStore((s) => s.setPaletteVisible)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const dragRef = useRef<{ ox: number; oy: number; sx: number; sy: number } | null>(null)

  useEffect(() => {
    const slot = document.getElementById('navPaletteSlot')
    if (!slot) return
    if (mode === 'docked') {
      slot.classList.remove('is-empty')
    } else {
      slot.classList.add('is-empty')
    }
  }, [mode])

  const head = (
    <div
      className="pal-head"
      id="paletteDragHandle"
      onPointerDown={(e) => {
        if (mode !== 'float') return
        dragRef.current = {
          ox: pos.x,
          oy: pos.y,
          sx: e.clientX,
          sy: e.clientY,
        }
        e.currentTarget.setPointerCapture(e.pointerId)
      }}
      onPointerMove={(e) => {
        if (!dragRef.current || mode !== 'float') return
        const dx = e.clientX - dragRef.current.sx
        const dy = e.clientY - dragRef.current.sy
        setPalettePos({
          x: Math.max(0, dragRef.current.ox + dx),
          y: Math.max(0, dragRef.current.oy + dy),
        })
      }}
      onPointerUp={() => {
        dragRef.current = null
      }}
    >
      <div className="pal-drag-grip" title="Drag tray" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="pal-label">
        <span className="pal-label-text">Panels</span>
        <span className="pal-mode">
          {mode === 'docked' ? 'Docked in nav' : 'Floating · drag to move'}
        </span>
      </div>
      <div className="pal-tools">
        <button
          type="button"
          title="Dock to main navigation"
          className={mode === 'docked' ? 'is-active' : ''}
          onClick={() => setPaletteMode('docked')}
        >
          ☰
        </button>
        <button
          type="button"
          title="Float freely"
          className={mode === 'float' ? 'is-active' : ''}
          onClick={() => setPaletteMode('float')}
        >
          ⬡
        </button>
        <button
          type="button"
          title="Hide tray"
          onClick={() => {
            setPaletteMode('chip')
            setPaletteVisible(false)
          }}
        >
          ×
        </button>
      </div>
    </div>
  )

  const buttons = PANEL_TYPES.map((type) => {
    const m = PANEL_META[type]
    return (
      <button
        key={type}
        type="button"
        className="pal-btn"
        data-open-panel={type}
        onClick={() => openPanelType(type)}
        title={m.label}
      >
        <span className="p-ico">{m.icon}</span>
        <span className="p-lab">{m.label}</span>
      </button>
    )
  })

  let node: React.ReactNode

  if (mode === 'chip' || !visible) {
    node = (
      <button
        type="button"
        className="panel-palette-chip"
        id="panelPaletteChip"
        title="Show panel tray"
        style={{ left: pos.x, top: pos.y }}
        onClick={() => {
          setPaletteMode('float')
          setPaletteVisible(true)
        }}
      >
        Panels
      </button>
    )
  } else if (mode === 'docked') {
    node = (
      <div className="panel-palette mode-docked" id="panelPalette" aria-label="Panel tray">
        {head}
        <div className="pal-btns">{buttons}</div>
      </div>
    )
  } else {
    node = (
      <div
        className="panel-palette mode-float"
        id="panelPalette"
        aria-label="Panel tray"
        style={{
          transform: `translate(${pos.x}px, ${pos.y}px)`,
        }}
      >
        {head}
        <div className="pal-btns">{buttons}</div>
        <div className="pal-hint">Click to open · drag tabs to dock</div>
      </div>
    )
  }

  if (typeof document === 'undefined') return null
  return createPortal(node, document.body)
}
