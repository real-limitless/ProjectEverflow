import { useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function EnvPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)
  const [sub, setSub] = useState<'env' | 'secrets'>('env')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="env" title={<TabTitleText>Env</TabTitleText>} />
          <Tab eventKey="secrets" title={<TabTitleText>Secrets</TabTitleText>} />
        </Tabs>
      </div>
      <div className="panel-scroll">
        {(sub === 'env' ? d.envVars : d.secrets).map((row) => (
          <div className="list-card" key={row.key}>
            <div className="lc-title" style={{ fontFamily: 'var(--mono)' }}>
              {row.key}
            </div>
            <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
              {row.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
