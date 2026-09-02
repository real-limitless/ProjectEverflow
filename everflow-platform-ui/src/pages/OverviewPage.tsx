import { PageSection } from '@patternfly/react-core'
import { ChartPanel } from '@/components/panels/ChartPanel'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function OverviewPage() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  return (
    <PageSection isFilled className="overview-chart" aria-labelledby="overview-title">
      <div className="overview-chart__intro">
        <h1 id="overview-title">Org chart</h1>
        <p>
          Add or remove bots, set their job and model pool, and pause a session from a seat.
          {currentProjectId ? '' : ' Open a project from Playground first.'}
        </p>
      </div>
      <div className="overview-chart__host">
        <ChartPanel embedded />
      </div>
    </PageSection>
  )
}
