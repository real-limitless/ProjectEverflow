import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { StatusLabel } from './statusLabel'

export function JobsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)

  return (
    <div className="panel-scroll">
      <div className="section-label">Background jobs</div>
      {d.jobs.map((j) => (
        <div className="list-card" key={j.title}>
          <div className="lc-row">
            <div className="lc-title">{j.title}</div>
            <StatusLabel status={j.status} />
          </div>
          <div className="lc-meta">{j.progress}</div>
        </div>
      ))}
    </div>
  )
}
