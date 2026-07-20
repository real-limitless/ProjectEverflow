import { useState } from 'react'
import { Button, Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { StatusLabel } from './statusLabel'

export function WorkflowsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)
  const [sub, setSub] = useState<'canvas' | 'runs' | 'triggers'>('canvas')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="canvas" title={<TabTitleText>Canvas</TabTitleText>} />
          <Tab eventKey="runs" title={<TabTitleText>Runs</TabTitleText>} />
          <Tab eventKey="triggers" title={<TabTitleText>Triggers</TabTitleText>} />
        </Tabs>
        <div style={{ display: 'flex', gap: 6 }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => alert('Demo: n8n import (common nodes only).')}
          >
            Import n8n
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() =>
              alert('Demo: would enqueue workflow run (202) + stream events.')
            }
          >
            Run
          </Button>
        </div>
      </div>
      <div className="panel-scroll">
        {sub === 'canvas' && (
          <>
            <div className="section-label">{d.projectName} · workflows</div>
            {d.workflows.map((w) => (
              <div className="list-card" key={w.name}>
                <div className="lc-row">
                  <div className="lc-title">{w.name}</div>
                  <StatusLabel status={w.status} />
                </div>
                <div className="lc-meta">
                  {w.trigger} · {w.runs} runs
                </div>
              </div>
            ))}
            <div className="section-label">Graph (selected)</div>
            <div className="wf-graph">
              {d.wfNodes.map((n, i) => (
                <span key={n.label} style={{ display: 'contents' }}>
                  {i ? <span className="wf-arrow">→</span> : null}
                  <span className={`wf-node ${n.cls}`}>{n.label}</span>
                </span>
              ))}
            </div>
            <p style={{ marginTop: 10, fontSize: 11, color: 'var(--text-dim)' }}>
              Demo placeholder — product uses React Flow + studio-worker runs.
            </p>
          </>
        )}
        {sub === 'runs' &&
          d.wfRuns.map((r) => (
            <div className="list-card" key={r.id}>
              <div className="lc-row">
                <div className="lc-title" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>
                  {r.id}
                </div>
                <StatusLabel status={r.status} />
              </div>
              <div className="lc-meta">
                {r.dur} · {r.when} · reconnectable SSE
              </div>
            </div>
          ))}
        {sub === 'triggers' &&
          d.workflows.map((w) => (
            <div className="list-card" key={w.name}>
              <div className="lc-title">{w.name}</div>
              <div className="lc-meta">
                Trigger: <code style={{ fontFamily: 'var(--mono)' }}>{w.trigger}</code>
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}
