import { useRef } from 'react'
import { usePlaygroundStore } from '@/store/playgroundStore'

interface DockSashProps {
  direction: 'horizontal' | 'vertical'
  sizes: number[]
  sashIndex: number
  pathToSplit: number[]
}

export function DockSash({
  direction,
  sizes,
  sashIndex,
  pathToSplit,
}: DockSashProps) {
  const resizeSplit = usePlaygroundStore((s) => s.resizeSplit)
  const startRef = useRef<{
    start: number
    sizes: number[]
    total: number
  } | null>(null)

  return (
    <div
      className="dock-sash"
      data-split-dir={direction}
      role="separator"
      aria-orientation={direction === 'horizontal' ? 'vertical' : 'horizontal'}
      onPointerDown={(e) => {
        const parent = e.currentTarget.parentElement
        if (!parent) return
        const rect = parent.getBoundingClientRect()
        startRef.current = {
          start: direction === 'horizontal' ? e.clientX : e.clientY,
          sizes: [...sizes],
          total: direction === 'horizontal' ? rect.width : rect.height,
        }
        e.currentTarget.classList.add('dragging')
        e.currentTarget.setPointerCapture(e.pointerId)
        e.preventDefault()
      }}
      onPointerMove={(e) => {
        if (!startRef.current) return
        const { start, sizes: startSizes, total } = startRef.current
        const delta =
          (((direction === 'horizontal' ? e.clientX : e.clientY) - start) /
            total) *
          100
        let a = startSizes[sashIndex] + delta
        let b = startSizes[sashIndex + 1] - delta
        const min = 12
        if (a < min) {
          b -= min - a
          a = min
        }
        if (b < min) {
          a -= min - b
          b = min
        }
        const next = [...startSizes]
        next[sashIndex] = a
        next[sashIndex + 1] = b
        // live flex update without full tree commit
        const parent = e.currentTarget.parentElement
        if (parent) {
          const children = parent.querySelectorAll(':scope > .dock-child')
          const c0 = children[sashIndex] as HTMLElement | undefined
          const c1 = children[sashIndex + 1] as HTMLElement | undefined
          if (c0) c0.style.flex = `${a} 1 0`
          if (c1) c1.style.flex = `${b} 1 0`
        }
        // store provisional for pointerup
        ;(e.currentTarget as HTMLElement).dataset.sizes = JSON.stringify(next)
      }}
      onPointerUp={(e) => {
        const raw = e.currentTarget.dataset.sizes
        e.currentTarget.classList.remove('dragging')
        startRef.current = null
        if (raw) {
          try {
            const next = JSON.parse(raw) as number[]
            resizeSplit(pathToSplit, next)
          } catch {
            /* ignore */
          }
          delete e.currentTarget.dataset.sizes
        }
      }}
      onPointerCancel={(e) => {
        e.currentTarget.classList.remove('dragging')
        startRef.current = null
      }}
    />
  )
}
