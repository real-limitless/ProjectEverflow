import { useMemo, useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import { basename } from '@/lib/fileTree'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { GitFileChange } from '@/types/project'

function statusClass(status: GitFileChange['status']): string {
  switch (status) {
    case 'A':
      return 'badge-a'
    case 'D':
      return 'badge-d'
    case 'M':
      return 'badge-m'
    case 'R':
      return 'badge-r'
    default:
      return 'badge-u'
  }
}

export function RepositoryPanel() {
  const [sub, setSub] = useState<'changes' | 'history' | 'issues'>('changes')
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = getProject(currentProjectId)
  const changes = p?.gitChanges || []

  const total = useMemo(
    () =>
      changes.reduce(
        (acc, c) => ({
          additions: acc.additions + c.additions,
          deletions: acc.deletions + c.deletions,
        }),
        { additions: 0, deletions: 0 },
      ),
    [changes],
  )

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
            {changes.length === 0 ? (
              <div className="code-empty-msg">No working-tree changes in this project.</div>
            ) : (
              <>
                <div className="change-row" style={{ opacity: 0.85, marginBlockEnd: '0.35rem' }}>
                  <span>
                    {changes.length} file{changes.length === 1 ? '' : 's'} changed
                  </span>
                  <span className="change-stats">
                    <span className="diff-add-n">+{total.additions}</span>
                    <span className="diff-del-n">−{total.deletions}</span>
                  </span>
                </div>
                {changes.map((c) => (
                  <div className="change-row" key={c.path} title={c.path}>
                    <span className={statusClass(c.status)}>{c.status}</span>
                    <span>{c.path}</span>
                    <span className="change-stats">
                      {c.additions > 0 && <span className="diff-add-n">+{c.additions}</span>}
                      {c.deletions > 0 && <span className="diff-del-n">−{c.deletions}</span>}
                    </span>
                  </div>
                ))}
                {changes
                  .filter((c) => c.diffPreview)
                  .map((c) => (
                    <div className="diff-block" key={`diff:${c.path}`}>
                      <div className="dh">{c.label || basename(c.path)}</div>
                      <pre>
                        {c.diffPreview!.split('\n').map((line, i) => {
                          let cls = ''
                          if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-add'
                          else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-del'
                          else if (line.startsWith('@@')) cls = 'diff-meta'
                          return (
                            <span key={i} className={cls || undefined}>
                              {line}
                              {'\n'}
                            </span>
                          )
                        })}
                      </pre>
                    </div>
                  ))}
              </>
            )}
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
