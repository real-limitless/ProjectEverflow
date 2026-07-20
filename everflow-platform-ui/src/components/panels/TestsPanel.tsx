import { Label } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function TestsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)

  return (
    <div className="panel-scroll">
      <div className="list-card">
        <div className="lc-row">
          <div className="lc-title">Latest run</div>
          <Label color={d.tests.failedN ? 'orange' : 'green'}>{d.tests.summary}</Label>
        </div>
      </div>
      {d.tests.failed.length > 0 && (
        <>
          <div className="section-label">Failed</div>
          {d.tests.failed.map((f) => (
            <div className="list-card" key={f}>
              <div className="lc-title" style={{ color: 'var(--pf-t--global--text--color--status--danger--default)' }}>
                {f}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
