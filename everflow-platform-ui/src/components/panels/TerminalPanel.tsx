import { useEffect, useState } from 'react'
import { Button } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function TerminalPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = getProject(currentProjectId)
  const [lines, setLines] = useState(p?.termLines || [])
  const [cmd, setCmd] = useState('')

  useEffect(() => {
    setLines(getProject(currentProjectId)?.termLines || [])
  }, [currentProjectId])

  const run = () => {
    const c = cmd.trim()
    if (!c) return
    setLines((prev) => [
      ...prev,
      { cls: 'cmd', text: ` ${c}` },
      { cls: 'muted', text: `demo: would run \`${c}\` in sandbox` },
      { cls: 'muted', text: 'sandbox@host:~$' },
    ])
    setCmd('')
  }

  return (
    <div className="term-wrap">
      <div className="term-toolbar">
        <span>sandbox · {p?.name}</span>
        <Button
          variant="link"
          size="sm"
          onClick={() => setLines(p?.termLines || [])}
        >
          Clear
        </Button>
      </div>
      <div className="term-output">
        {lines.map((l, i) => (
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
          placeholder="type a command…"
          aria-label="Terminal input"
        />
      </div>
    </div>
  )
}
