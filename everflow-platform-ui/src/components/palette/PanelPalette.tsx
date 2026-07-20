import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { PANEL_META } from '@/data/panelMeta'
import { PANEL_TYPES } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'

function getSlot(): HTMLElement | null {
  return document.getElementById('navPaletteSlot')
}

function isOverSidebarDrop(clientX: number, clientY: number): boolean {
  const sidebar = document.getElementById('sidebar')
  const slot = getSlot()
  if (slot && !slot.classList.contains('is-empty')) {
    const r = slot.getBoundingClientRect()
    if (
      clientX >= r.left &&
      clientX <= r.right &&
      clientY >= r.top &&
      clientY <= r.bottom
    ) {
      return true
    }
  }
  if (!sidebar) return false
  const sr = sidebar.getBoundingClientRect()
  return (
    clientX >= sr.left &&
    clientX <= sr.right &&
    clientY >= sr.top &&
    clientY <= sr.bottom
  )
}

export function PanelPalette() {
  const mode = usePlaygroundStore((s) => s.paletteMode)
  const pos = usePlaygroundStore((s) => s.palettePos)
  const visible = usePlaygroundStore((s) => s.paletteVisible)
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)
  const paletteDragging = usePlaygroundStore((s) => s.paletteDragging)
  const setPaletteMode = usePlaygroundStore((s) => s.setPaletteMode)
  const setPalettePos = usePlaygroundStore((s) => s.setPalettePos)
  const setPaletteVisible = usePlaygroundStore((s) => s.setPaletteVisible)
  const setPaletteDragging = usePlaygroundStore((s) => s.setPaletteDragging)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)

  const dragRef = useRef<{
    ox: number
    oy: number
    sx: number
    sy: number
    fromDocked: boolean
    moved: boolean
  } | null>(null)

  const [slotEl, setSlotEl] = useState<HTMLElement | null>(null)
  const [dropHot, setDropHot] = useState(false)

  // Keep portal target in sync; clear empty class when docking
  useLayoutEffect(() => {
    const slot = getSlot()
    setSlotEl(slot)
    if (!slot) return
    if (mode === 'docked' || paletteDragging) {
      slot.classList.remove('is-empty')
    } else {
      slot.classList.add('is-empty')
      slot.classList.remove('is-drop-hot')
    }
    slot.classList.toggle('is-dragging-palette', paletteDragging)
    slot.classList.toggle('is-drop-hot', dropHot && paletteDragging)
  }, [mode, paletteDragging, dropHot])

  const dockToSidebar = () => {
    const slot = getSlot()
    if (slot) {
      slot.classList.remove('is-empty')
      setSlotEl(slot)
    }
    setPaletteVisible(true)
    setPaletteMode('docked')
  }

  const floatPalette = () => {
    setPaletteVisible(true)
    setPaletteMode('float')
  }

  const hidePalette = () => {
    // Park chip where users can always find it (bottom-left near sidebar)
    const safeX = 10
    const safeY = Math.max(72, window.innerHeight - 56)
    setPalettePos({ x: safeX, y: safeY })
    setPaletteVisible(false)
    setPaletteMode('chip')
  }

  const endDrag = (clientX: number, clientY: number) => {
    const state = dragRef.current
    dragRef.current = null
    setPaletteDragging(false)
    setDropHot(false)

    if (!state || !state.moved) return

    if (isOverSidebarDrop(clientX, clientY)) {
      dockToSidebar()
    } else if (state.fromDocked) {
      setPalettePos({
        x: Math.max(0, clientX - 40),
        y: Math.max(0, clientY - 16),
      })
      floatPalette()
    }
  }

  const tools = (
    <div className="pal-tools" onPointerDown={(e) => e.stopPropagation()}>
      <button
        type="button"
        title="Dock to sidebar"
        className={mode === 'docked' ? 'is-active' : ''}
        onClick={(e) => {
          e.stopPropagation()
          dockToSidebar()
        }}
      >
        ☰
      </button>
      <button
        type="button"
        title="Float freely"
        className={mode === 'float' ? 'is-active' : ''}
        onClick={(e) => {
          e.stopPropagation()
          floatPalette()
        }}
      >
        ⬡
      </button>
      <button
        type="button"
        title="Hide tray"
        onClick={(e) => {
          e.stopPropagation()
          hidePalette()
        }}
      >
        ×
      </button>
    </div>
  )

  const dragHandle = (
    <div
      className="pal-drag-handle"
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest('button')) return
        dragRef.current = {
          ox: mode === 'float' ? pos.x : e.clientX,
          oy: mode === 'float' ? pos.y : e.clientY,
          sx: e.clientX,
          sy: e.clientY,
          fromDocked: mode === 'docked',
          moved: false,
        }
        setPaletteDragging(true)
        e.currentTarget.setPointerCapture(e.pointerId)
      }}
      onPointerMove={(e) => {
        if (!dragRef.current) return
        const dist =
          Math.abs(e.clientX - dragRef.current.sx) +
          Math.abs(e.clientY - dragRef.current.sy)
        if (dist > 4) dragRef.current.moved = true

        if (mode === 'float') {
          const dx = e.clientX - dragRef.current.sx
          const dy = e.clientY - dragRef.current.sy
          setPalettePos({
            x: Math.max(0, dragRef.current.ox + dx),
            y: Math.max(0, dragRef.current.oy + dy),
          })
        } else if (dragRef.current.fromDocked && dist > 8) {
          setPalettePos({
            x: Math.max(0, e.clientX - 40),
            y: Math.max(0, e.clientY - 16),
          })
          setPaletteMode('float')
          dragRef.current = {
            ox: e.clientX - 40,
            oy: e.clientY - 16,
            sx: e.clientX,
            sy: e.clientY,
            fromDocked: true,
            moved: true,
          }
        }

        setDropHot(isOverSidebarDrop(e.clientX, e.clientY))
      }}
      onPointerUp={(e) => endDrag(e.clientX, e.clientY)}
      onPointerCancel={(e) => endDrag(e.clientX, e.clientY)}
    >
      <div className="pal-drag-grip" title="Drag tray" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="pal-label">
        <span className="pal-label-text">Panels</span>
        <span className="pal-mode">
          {mode === 'docked'
            ? 'In sidebar · drag out to float'
            : 'Drag into sidebar to dock'}
        </span>
      </div>
    </div>
  )

  const head = (
    <div className="pal-head">
      {dragHandle}
      {tools}
    </div>
  )

  const buttons = (
    <div className="pal-btns">
      {PANEL_TYPES.map((type) => {
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
      })}
    </div>
  )

  let node: React.ReactNode

  if (mode === 'chip' || !visible) {
    // Sidebar footer already has a Panels button when nav is open — no floater
    if (isSidebarOpen) {
      node = null
    } else {
      const chipX = Number.isFinite(pos.x) ? pos.x : 10
      const chipY = Number.isFinite(pos.y)
        ? pos.y
        : Math.max(72, window.innerHeight - 56)
      node = (
        <button
          type="button"
          className="panel-palette-chip is-visible"
          id="panelPaletteChip"
          title="Show panel tray"
          style={{ left: chipX, top: chipY }}
          onClick={() => floatPalette()}
        >
          Panels
        </button>
      )
    }
  } else if (mode === 'docked') {
    node = (
      <div
        className="docked-panel-rail"
        id="panelPalette"
        aria-label="Open a panel"
      >
        <div className="docked-panel-rail__head">
          <div
            className="docked-panel-rail__grip pal-drag-handle"
            title="Drag to undock"
            onPointerDown={(e) => {
              if ((e.target as HTMLElement).closest('button')) return
              dragRef.current = {
                ox: e.clientX,
                oy: e.clientY,
                sx: e.clientX,
                sy: e.clientY,
                fromDocked: true,
                moved: false,
              }
              setPaletteDragging(true)
              e.currentTarget.setPointerCapture(e.pointerId)
            }}
            onPointerMove={(e) => {
              if (!dragRef.current) return
              const dist =
                Math.abs(e.clientX - dragRef.current.sx) +
                Math.abs(e.clientY - dragRef.current.sy)
              if (dist > 4) dragRef.current.moved = true
              if (dragRef.current.fromDocked && dist > 8) {
                setPalettePos({
                  x: Math.max(0, e.clientX - 40),
                  y: Math.max(0, e.clientY - 16),
                })
                setPaletteMode('float')
                dragRef.current = {
                  ox: e.clientX - 40,
                  oy: e.clientY - 16,
                  sx: e.clientX,
                  sy: e.clientY,
                  fromDocked: true,
                  moved: true,
                }
              }
              setDropHot(isOverSidebarDrop(e.clientX, e.clientY))
            }}
            onPointerUp={(e) => endDrag(e.clientX, e.clientY)}
            onPointerCancel={(e) => endDrag(e.clientX, e.clientY)}
          >
            <span className="docked-panel-rail__title">Open panel</span>
          </div>
          <div className="docked-panel-rail__tools">
            <button
              type="button"
              title="Float tray"
              onClick={(e) => {
                e.stopPropagation()
                floatPalette()
              }}
            >
              ⬡
            </button>
            <button
              type="button"
              title="Hide tray"
              onClick={(e) => {
                e.stopPropagation()
                hidePalette()
              }}
            >
              ×
            </button>
          </div>
        </div>
        <ul className="docked-panel-rail__list" role="list">
          {PANEL_TYPES.map((type) => {
            const m = PANEL_META[type]
            return (
              <li key={type}>
                <button
                  type="button"
                  className="docked-panel-rail__item"
                  data-open-panel={type}
                  onClick={() => openPanelType(type)}
                  title={m.label}
                >
                  <span className="docked-panel-rail__ico" aria-hidden>
                    {m.icon}
                  </span>
                  <span className="docked-panel-rail__lab">{m.label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    )
  } else {
    node = (
      <div
        className="panel-palette mode-float"
        id="panelPalette"
        aria-label="Panel tray"
        style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
      >
        {head}
        {buttons}
        <div className="pal-hint">Drag into left sidebar to pin · ☰ docks</div>
      </div>
    )
  }

  if (typeof document === 'undefined') return null

  if (mode === 'docked') {
    const target = slotEl || getSlot()
    if (target) return createPortal(node, target)
  }

  return createPortal(node, document.body)
}
