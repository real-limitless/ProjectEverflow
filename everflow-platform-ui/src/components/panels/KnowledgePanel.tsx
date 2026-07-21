import { useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio } from '@/store/studioDemoStore'
import { CanvasTab } from './knowledge/CanvasTab'
import { MindMapsTab } from './knowledge/MindMapsTab'
import { WebSearchTab } from './knowledge/WebSearchTab'

export function KnowledgePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const state = useProjectStudio(projectId)
  const [sub, setSub] = useState<'canvas' | 'web' | 'mind'>('canvas')

  return (
    <div className="knowledge-panel-root">
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="canvas" title={<TabTitleText>Canvas</TabTitleText>} />
          <Tab eventKey="web" title={<TabTitleText>Web search</TabTitleText>} />
          <Tab eventKey="mind" title={<TabTitleText>Mind maps</TabTitleText>} />
        </Tabs>
      </div>
      <div
        className={
          sub === 'canvas' || sub === 'mind'
            ? 'knowledge-panel-body knowledge-panel-body--fill'
            : 'panel-scroll knowledge-panel-body'
        }
      >
        {sub === 'canvas' && <CanvasTab projectId={projectId} canvases={state.canvases} />}
        {sub === 'web' && <WebSearchTab projectId={projectId} />}
        {sub === 'mind' && <MindMapsTab projectId={projectId} mindMaps={state.mindMaps} />}
      </div>
    </div>
  )
}
