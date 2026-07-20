import { Label } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function ToolsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)

  return (
    <div className="panel-scroll">
      <div className="section-label">HTTP tools</div>
      {d.httpTools.map((t) => (
        <div className="list-card" key={t.name}>
          <div className="lc-row">
            <div className="lc-title" style={{ fontFamily: 'var(--mono)' }}>
              {t.name}
            </div>
            <Label color={t.on ? 'green' : 'grey'}>{t.method}</Label>
          </div>
        </div>
      ))}
      <div className="section-label">MCP servers</div>
      {d.mcps.map((m) => (
        <div className="list-card" key={m.name}>
          <div className="lc-row">
            <div className="lc-title">{m.name}</div>
            <Label color={m.on ? 'green' : 'grey'}>{m.on ? 'on' : 'off'}</Label>
          </div>
          <div className="lc-meta">{m.transport}</div>
        </div>
      ))}
    </div>
  )
}
