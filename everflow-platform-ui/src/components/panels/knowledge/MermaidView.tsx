import { useEffect, useId, useRef, useState } from 'react'

interface MermaidViewProps {
  source: string
  className?: string
}

let mermaidReady: Promise<typeof import('mermaid')> | null = null

function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import('mermaid').then(async (mod) => {
      mod.default.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'neutral',
        fontFamily: 'inherit',
      })
      return mod
    })
  }
  return mermaidReady
}

export function MermaidView({ source, className }: MermaidViewProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const reactId = useId().replace(/:/g, '')
  const [error, setError] = useState<string | null>(null)
  const [rendering, setRendering] = useState(false)

  useEffect(() => {
    let cancelled = false
    const host = hostRef.current
    if (!host) return

    const run = async () => {
      const trimmed = source.trim()
      if (!trimmed) {
        host.innerHTML = ''
        setError(null)
        return
      }
      setRendering(true)
      setError(null)
      try {
        const mod = await loadMermaid()
        if (cancelled) return
        const id = `mm-${reactId}-${Math.random().toString(36).slice(2, 8)}`
        const { svg } = await mod.default.render(id, trimmed)
        if (cancelled) return
        host.innerHTML = svg
      } catch (e) {
        if (cancelled) return
        host.innerHTML = ''
        setError(e instanceof Error ? e.message : 'Invalid Mermaid diagram')
      } finally {
        if (!cancelled) setRendering(false)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [source, reactId])

  return (
    <div className={`mermaid-host ${className || ''}`.trim()}>
      {rendering && <div className="mermaid-status">Rendering diagram…</div>}
      {error && (
        <div className="mermaid-error" role="alert">
          {error}
        </div>
      )}
      <div ref={hostRef} className="mermaid-svg" />
    </div>
  )
}
