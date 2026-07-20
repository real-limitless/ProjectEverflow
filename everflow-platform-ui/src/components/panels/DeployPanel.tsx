import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { StatusLabel } from './statusLabel'

export function DeployPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)

  return (
    <div className="panel-scroll">
      <div className="section-label">Environments</div>
      {d.deploys.map((dep) => (
        <div className="list-card" key={dep.env}>
          <div className="lc-row">
            <div className="lc-title">{dep.env}</div>
            <StatusLabel status={dep.status} />
          </div>
          <div className="lc-meta">
            {dep.url} · {dep.when}
          </div>
        </div>
      ))}
      <div className="section-label">Timeline</div>
      {d.deployTimeline.map((t) => (
        <div className="list-card" key={t.time + t.msg}>
          <div className="lc-title">{t.msg}</div>
          <div className="lc-meta">{t.time}</div>
        </div>
      ))}
    </div>
  )
}
