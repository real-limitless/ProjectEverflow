import { useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function KnowledgePanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = PROJECTS[currentProjectId]
  const [sub, setSub] = useState<'files' | 'canvas' | 'rag'>('files')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="files" title={<TabTitleText>Files</TabTitleText>} />
          <Tab eventKey="canvas" title={<TabTitleText>Canvas</TabTitleText>} />
          <Tab eventKey="rag" title={<TabTitleText>RAG</TabTitleText>} />
        </Tabs>
      </div>
      <div className="panel-scroll">
        {sub === 'files' &&
          p?.knowledgeFiles.map((f) => (
            <div className="list-card" key={f.path}>
              <div className="lc-title">{f.name}</div>
              <div className="lc-meta">{f.path}</div>
            </div>
          ))}
        {sub === 'canvas' &&
          p?.canvases.map((c) => (
            <div className="list-card" key={c.name}>
              <div className="lc-title">{c.name}</div>
              <div className="lc-meta">{c.desc}</div>
            </div>
          ))}
        {sub === 'rag' && (
          <div className="list-card">
            <div className="lc-title">Code index · pgvector</div>
            <div className="lc-meta">
              Demo: hybrid search over repo embeddings + docs. Connect everflow-ai-workspace.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
