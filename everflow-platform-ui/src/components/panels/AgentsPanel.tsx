import { Label } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function AgentsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)

  return (
    <div className="panel-scroll">
      <div className="section-label">Agents</div>
      {d.agents.map((a) => (
        <div className="list-card" key={a.id}>
          <div className="lc-row">
            <div className="lc-title">{a.name}</div>
            {a.active ? <Label color="green">active</Label> : <Label color="grey">idle</Label>}
          </div>
          <div className="lc-meta">{a.desc}</div>
        </div>
      ))}
    </div>
  )
}
