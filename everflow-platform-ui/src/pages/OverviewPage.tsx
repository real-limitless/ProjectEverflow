import { PageSection } from '@patternfly/react-core'
import { ChartPanel } from '@/components/panels/ChartPanel'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function OverviewPage() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  return (
    <>
      <PageSection aria-labelledby="overview-title">
        <h1 id="overview-title">Org chart</h1>
        <p>
          The org chart is the control plane. Add or remove bots, set their job and model
          pool, and pause a session from a seat.{' '}
          {currentProjectId ? '' : 'Open a project from Playground first.'}
        </p>
      </PageSection>
      <PageSection isFilled className="overview-chart">
        <div className="overview-chart__host">
          <ChartPanel />
        </div>
      </PageSection>
    </>
  )
}
