import { useEffect } from 'react'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { SurfaceMode } from '@/types/org'

const MODES: { id: SurfaceMode; label: string }[] = [
  { id: 'room', label: 'Room' },
  { id: 'harness', label: 'Harness' },
  { id: 'chart', label: 'Chart' },
]

export function TripleModeToggle() {
  const surfaceMode = usePlaygroundStore((s) => s.surfaceMode)
  const setSurfaceMode = usePlaygroundStore((s) => s.setSurfaceMode)
  const cycleSurfaceMode = usePlaygroundStore((s) => s.cycleSurfaceMode)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '.') {
        e.preventDefault()
        cycleSurfaceMode()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cycleSurfaceMode])

  return (
    <div className="triple-mode" role="tablist" aria-label="Room, Harness, Chart">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          role="tab"
          aria-selected={surfaceMode === m.id}
          className={`triple-mode__btn${surfaceMode === m.id ? ' is-active' : ''}`}
          onClick={() => setSurfaceMode(m.id)}
        >
          {m.label}
        </button>
      ))}
      <span className="triple-mode__hint">⌘.</span>
    </div>
  )
}
