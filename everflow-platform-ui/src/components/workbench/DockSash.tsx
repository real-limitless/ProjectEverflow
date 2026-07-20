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
  const latestSizes = useRef<number[] | null>(null)

  const getSplitEl = (el: HTMLElement) =>
    el.closest('.dock-split') as HTMLElement | null

  const applyLive = (splitEl: HTMLElement, next: number[]) => {
    const children = splitEl.querySelectorAll<HTMLElement>(':scope > .dock-child')
    const c0 = children[sashIndex]
    const c1 = children[sashIndex + 1]
    if (c0) c0.style.flex = `${next[sashIndex]} 1 0`
    if (c1) c1.style.flex = `${next[sashIndex + 1]} 1 0`
  }

  return (
    <div
      className={`dock-sash dock-sash--${direction}`}
      data-split-dir={direction}
      role="separator"
      aria-orientation={direction === 'horizontal' ? 'vertical' : 'horizontal'}
      aria-label={
        direction === 'horizontal' ? 'Resize panels horizontally' : 'Resize panels vertically'
      }
      onPointerDown={(e) => {
        const splitEl = getSplitEl(e.currentTarget)
        if (!splitEl) return
        const rect = splitEl.getBoundingClientRect()
        const total =
          direction === 'horizontal' ? rect.width : rect.height
        if (total <= 0) return
        startRef.current = {
          start: direction === 'horizontal' ? e.clientX : e.clientY,
          sizes: [...sizes],
          total,
        }
        latestSizes.current = [...sizes]
        e.currentTarget.classList.add('dragging')
        e.currentTarget.setPointerCapture(e.pointerId)
        document.body.classList.add('is-sash-dragging')
        e.preventDefault()
        e.stopPropagation()
      }}
      onPointerMove={(e) => {
        if (!startRef.current) return
        const splitEl = getSplitEl(e.currentTarget)
        if (!splitEl) return
        const { start, sizes: startSizes, total } = startRef.current
        const pos = direction === 'horizontal' ? e.clientX : e.clientY
        const delta = ((pos - start) / total) * 100
        let a = startSizes[sashIndex] + delta
        let b = startSizes[sashIndex + 1] - delta
        const min = 10
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
        latestSizes.current = next
        applyLive(splitEl, next)
      }}
      onPointerUp={(e) => {
        e.currentTarget.classList.remove('dragging')
        document.body.classList.remove('is-sash-dragging')
        startRef.current = null
        const next = latestSizes.current
        latestSizes.current = null
        if (next) {
          resizeSplit(pathToSplit, next)
        }
      }}
      onPointerCancel={(e) => {
        e.currentTarget.classList.remove('dragging')
        document.body.classList.remove('is-sash-dragging')
        startRef.current = null
        latestSizes.current = null
      }}
    />
  )
}
