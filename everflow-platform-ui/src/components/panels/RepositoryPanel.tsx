import { useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'

export function RepositoryPanel() {
  const [sub, setSub] = useState<'changes' | 'history' | 'issues'>('changes')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="repo-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="changes" title={<TabTitleText>Changes</TabTitleText>} />
          <Tab eventKey="history" title={<TabTitleText>History</TabTitleText>} />
          <Tab eventKey="issues" title={<TabTitleText>Issues</TabTitleText>} />
        </Tabs>
      </div>
      <div className="repo-body">
        {sub === 'changes' && (
          <>
            <div className="change-row">
              <span className="badge-m">M</span>
              <span>src/components/dashboard/MetricCard.tsx</span>
            </div>
            <div className="change-row">
              <span className="badge-a">A</span>
              <span>docs/runbook.md</span>
            </div>
            <div className="diff-block">
              <div className="dh">MetricCard.tsx</div>
              <pre>
                <span className="diff-meta">@@ -12,3 +12,6 @@</span>
                {'\n'}
                <span className="diff-del">
                  - const status = pct &lt; 80 ? &quot;healthy&quot; : &quot;critical&quot;;
                </span>
                {'\n'}
                <span className="diff-add">+ const status =</span>
                {'\n'}
                <span className="diff-add">+ pct &gt;= 90 ? &quot;critical&quot; :</span>
                {'\n'}
                <span className="diff-add">
                  + pct &gt;= 65 ? &quot;warning&quot; : &quot;healthy&quot;;
                </span>
              </pre>
            </div>
          </>
        )}
        {sub === 'history' && (
          <>
            <div className="history-item">
              <span className="hash">a91f3c2</span>
              <div>
                <div className="msg">fix MetricCard warning threshold</div>
                <div className="who">you · 2m ago</div>
              </div>
            </div>
            <div className="history-item">
              <span className="hash">b02e881</span>
              <div>
                <div className="msg">Wire nginx health checks</div>
                <div className="who">you · yesterday</div>
              </div>
            </div>
          </>
        )}
        {sub === 'issues' && (
          <div className="issue-card">
            <h4>#42 MetricCard warning at 67%</h4>
            <div className="issue-meta">open · labeled bug · updated 2m ago</div>
            <div className="issue-comment">
              <strong>agent</strong>: Thresholds updated in PR draft — see Changes.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
