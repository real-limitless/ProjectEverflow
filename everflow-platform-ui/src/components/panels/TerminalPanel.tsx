import { useEffect, useMemo, useState } from 'react'
import { Button } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { TerminalLine, TerminalSession } from '@/types/studio'

function newSession(index: number, seed?: TerminalLine[]): TerminalSession {
  return {
    id: `sh-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 5)}`,
    name: index === 0 ? 'bash' : `shell-${index + 1}`,
    lines: seed?.length
      ? [...seed]
      : [
          { cls: 'muted', text: `sandbox session · ${index === 0 ? 'bash' : `shell-${index + 1}`}` },
          { cls: 'muted', text: 'sandbox@host:~$' },
        ],
    history: [],
  }
}

export function TerminalPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = getProject(currentProjectId)
  const seedLines = useMemo(() => p?.termLines || [], [p?.termLines])

  const [sessions, setSessions] = useState<TerminalSession[]>(() => [newSession(0, seedLines)])
  const [activeId, setActiveId] = useState(() => sessions[0]?.id ?? '')
  const [cmd, setCmd] = useState('')

  useEffect(() => {
    // Reset when project changes: keep multi-session UX, reseed first shell
    const first = newSession(0, getProject(currentProjectId)?.termLines || [])
    setSessions([first])
    setActiveId(first.id)
    setCmd('')
  }, [currentProjectId])

  const active = sessions.find((s) => s.id === activeId) ?? sessions[0]

  const updateActive = (fn: (s: TerminalSession) => TerminalSession) => {
    if (!active) return
    setSessions((prev) => prev.map((s) => (s.id === active.id ? fn(s) : s)))
  }

  const run = () => {
    const c = cmd.trim()
    if (!c || !active) return
    updateActive((s) => ({
      ...s,
      history: [...s.history, c],
      lines: [
        ...s.lines,
        { cls: 'cmd', text: ` ${c}` },
        { cls: 'muted', text: `demo: would run \`${c}\` in sandbox (${s.name})` },
        { cls: 'muted', text: `${s.name}@host:~$` },
      ],
    }))
    setCmd('')
  }

  const addSession = () => {
    const s = newSession(sessions.length)
    setSessions((prev) => [...prev, s])
    setActiveId(s.id)
  }

  const closeSession = (id: string) => {
    setSessions((prev) => {
      if (prev.length <= 1) return prev
      const next = prev.filter((s) => s.id !== id)
      if (activeId === id) setActiveId(next[0]?.id ?? '')
      return next
    })
  }

  const clearActive = () => {
    updateActive((s) => ({
      ...s,
      lines: [
        { cls: 'muted', text: `cleared · ${s.name}` },
        { cls: 'muted', text: `${s.name}@host:~$` },
      ],
    }))
  }

  return (
    <div className="term-wrap">
      <div className="term-toolbar">
        <span>
          sandbox · {p?.name} · {sessions.length} shell{sessions.length === 1 ? '' : 's'}
        </span>
        <Button variant="link" size="sm" onClick={clearActive}>
          Clear
        </Button>
      </div>
      <div className="term-session-strip" role="tablist" aria-label="Terminal sessions">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`term-session-pill ${s.id === active?.id ? 'is-active' : ''}`}
            role="tab"
            aria-selected={s.id === active?.id}
            onClick={() => setActiveId(s.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') setActiveId(s.id)
            }}
            tabIndex={0}
          >
            <span>{s.name}</span>
            {sessions.length > 1 && (
              <button
                type="button"
                className="term-session-close"
                aria-label={`Close ${s.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  closeSession(s.id)
                }}
              >
                ×
              </button>
            )}
          </div>
        ))}
        <Button variant="plain" size="sm" onClick={addSession} aria-label="New shell">
          +
        </Button>
      </div>
      <div className="term-output">
        {(active?.lines ?? []).map((l, i) => (
          <div key={i} className={l.cls}>
            {l.text}
          </div>
        ))}
      </div>
      <div className="term-input-row">
        <span className="prompt">$</span>
        <input
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') run()
          }}
          placeholder={`type a command in ${active?.name ?? 'shell'}…`}
          aria-label="Terminal input"
        />
      </div>
    </div>
  )
}
