import { useState } from 'react'
import { Button, Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function PreviewPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = PROJECTS[currentProjectId]
  const [device, setDevice] = useState<'desktop' | 'tablet' | 'mobile'>('desktop')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={device}
          onSelect={(_e, k) => setDevice(k as typeof device)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="desktop" title={<TabTitleText>Desktop</TabTitleText>} />
          <Tab eventKey="tablet" title={<TabTitleText>Tablet</TabTitleText>} />
          <Tab eventKey="mobile" title={<TabTitleText>Mobile</TabTitleText>} />
        </Tabs>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => alert('Demo: refresh sandbox preview')}
        >
          Refresh
        </Button>
      </div>
      <div className="panel-scroll preview-frame">
        <div className={`preview-device ${device}`}>
          <div className="preview-chrome">
            <span className="dot r" />
            <span className="dot y" />
            <span className="dot g" />
            <span className="url">
              localhost:5173 · {p?.name || 'preview'}
            </span>
          </div>
          <div className="preview-body">
            <div className="preview-hero">
              <h1>{p?.name || 'App'}</h1>
              <p>Live sandbox preview (demo). Connect WebContainers or Docker later.</p>
              <div className="preview-metrics">
                <div className="metric ok">
                  <span className="m-val">42%</span>
                  <span className="m-lab">CPU</span>
                </div>
                <div className="metric warn">
                  <span className="m-val">67%</span>
                  <span className="m-lab">Memory</span>
                </div>
                <div className="metric ok">
                  <span className="m-val">12</span>
                  <span className="m-lab">Containers</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
