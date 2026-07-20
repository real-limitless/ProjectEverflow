import { useMemo, useState } from 'react'
import {
  Button,
  FormGroup,
  Label,
  TextArea,
  TextInput,
  Tabs,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import { basename } from '@/lib/fileTree'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { GitFileChange } from '@/types/project'
import type { IssueStatus, PullRequest, RepoIssue } from '@/types/studio'

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
  const [sub, setSub] = useState<'changes' | 'history' | 'prs' | 'issues' | 'graph'>('changes')
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const projectId = currentProjectId || 'default'
  const p = getProject(currentProjectId)
  const changes = p?.gitChanges || []
  const studio = useProjectStudio(projectId)
  const createIssue = useStudioDemoStore((s) => s.createIssue)
  const updateIssue = useStudioDemoStore((s) => s.updateIssue)
  const deleteIssue = useStudioDemoStore((s) => s.deleteIssue)
  const createPr = useStudioDemoStore((s) => s.createPr)

  const [selectedPath, setSelectedPath] = useState(changes[0]?.path ?? '')
  const [staged, setStaged] = useState<Record<string, boolean>>({})
  const [issueFilter, setIssueFilter] = useState<'all' | IssueStatus>('open')
  const [selectedIssue, setSelectedIssue] = useState<RepoIssue | null>(null)
  const [selectedPr, setSelectedPr] = useState<PullRequest | null>(null)
  const [selectedCommitId, setSelectedCommitId] = useState(studio.commits[0]?.id ?? '')

  const [issueOpen, setIssueOpen] = useState(false)
  const [prOpen, setPrOpen] = useState(false)
  const [issueTitle, setIssueTitle] = useState('')
  const [issueBody, setIssueBody] = useState('')
  const [issueLabels, setIssueLabels] = useState('bug')
  const [prTitle, setPrTitle] = useState('')
  const [prBody, setPrBody] = useState('')
  const [prBase, setPrBase] = useState('main')
  const [prHead, setPrHead] = useState('feature/branch')
  const [editBody, setEditBody] = useState('')

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

  const selectedChange = changes.find((c) => c.path === selectedPath) ?? changes[0]
  const issues = studio.issues.filter((i) => issueFilter === 'all' || i.status === issueFilter)
  const selectedCommit = studio.commits.find((c) => c.id === selectedCommitId) ?? studio.commits[0]

  // lane assignment by branch label presence
  const graphLanes = useMemo(() => {
    const branchLane = new Map<string, number>()
    let next = 0
    return studio.commits.map((c) => {
      const label = c.branchLabels.find((b) => b !== 'HEAD') || c.branchLabels[0] || 'main'
      if (!branchLane.has(label)) branchLane.set(label, next++)
      return { commit: c, lane: branchLane.get(label) ?? 0 }
    })
  }, [studio.commits])

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
          <Tab eventKey="prs" title={<TabTitleText>Pull requests</TabTitleText>} />
          <Tab eventKey="issues" title={<TabTitleText>Issues</TabTitleText>} />
          <Tab eventKey="graph" title={<TabTitleText>Graph</TabTitleText>} />
        </Tabs>
      </div>
      <div className="repo-body" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
        {sub === 'changes' && (
          changes.length === 0 ? (
            <EmptySplash title="Clean working tree" body="No working-tree changes in this project." />
          ) : (
            <div className="repo-changes-layout">
              <div className="repo-changes-list">
                <div className="change-row" style={{ opacity: 0.85, marginBlockEnd: '0.35rem', cursor: 'default' }}>
                  <span>
                    {changes.length} file{changes.length === 1 ? '' : 's'}
                  </span>
                  <span className="change-stats">
                    <span className="diff-add-n">+{total.additions}</span>
                    <span className="diff-del-n">−{total.deletions}</span>
                  </span>
                </div>
                {changes.map((c) => (
                  <div
                    key={c.path}
                    className={`change-row ${selectedChange?.path === c.path ? 'is-selected' : ''}`}
                    onClick={() => setSelectedPath(c.path)}
                  >
                    <span className={statusClass(c.status)}>{c.status}</span>
                    <span className="change-path" title={c.path}>
                      {c.path}
                    </span>
                    <Button
                      variant="link"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        setStaged((s) => ({ ...s, [c.path]: !s[c.path] }))
                      }}
                    >
                      {staged[c.path] ? 'Unstage' : 'Stage'}
                    </Button>
                  </div>
                ))}
              </div>
              <div className="repo-changes-diff">
                {selectedChange?.diffPreview ? (
                  <div className="diff-block">
                    <div className="dh">
                      {selectedChange.label || basename(selectedChange.path)}
                      {staged[selectedChange.path] ? ' · staged' : ' · unstaged'}
                    </div>
                    <pre>
                      {selectedChange.diffPreview.split('\n').map((line, i) => {
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
                ) : (
                  <div className="code-empty-msg">Select a file with a diff preview.</div>
                )}
              </div>
            </div>
          )
        )}

        {sub === 'history' && (
          <div className="repo-changes-layout">
            <div className="repo-changes-list">
              {studio.commits.map((c) => (
                <div
                  key={c.id}
                  className={`history-item ${selectedCommit?.id === c.id ? 'is-selected' : ''}`}
                  style={{
                    cursor: 'pointer',
                    padding: '0.4rem',
                    borderRadius: 4,
                    background:
                      selectedCommit?.id === c.id
                        ? 'var(--pf-t--global--background--color--secondary--default)'
                        : undefined,
                  }}
                  onClick={() => setSelectedCommitId(c.id)}
                >
                  <span className="hash">{c.shortHash}</span>
                  <div>
                    <div className="msg">{c.message}</div>
                    <div className="who">
                      {c.author} · {c.when}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="repo-changes-diff">
              {selectedCommit && (
                <div className="list-card">
                  <div className="lc-title">{selectedCommit.message}</div>
                  <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                    {selectedCommit.hash}
                  </div>
                  <div className="lc-meta">
                    {selectedCommit.author} · {selectedCommit.when}
                  </div>
                  {selectedCommit.branchLabels.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      {selectedCommit.branchLabels.map((b) => (
                        <span key={b} className="git-branch-tag">
                          {b}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="section-label">Files</div>
                  {selectedCommit.files.map((f) => (
                    <div key={f} className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                      {f}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {sub === 'prs' && (
          <div className="repo-changes-layout">
            <div className="repo-changes-list">
              <Button variant="primary" size="sm" style={{ marginBottom: 8 }} onClick={() => setPrOpen(true)}>
                Create pull request
              </Button>
              {studio.pullRequests.map((pr) => (
                <div
                  key={pr.id}
                  className="list-card"
                  style={{
                    cursor: 'pointer',
                    outline:
                      selectedPr?.id === pr.id
                        ? '2px solid var(--pf-t--global--border--color--brand--default)'
                        : undefined,
                  }}
                  onClick={() => setSelectedPr(pr)}
                >
                  <div className="lc-row">
                    <div className="lc-title">
                      #{pr.number} {pr.title}
                    </div>
                    <Label
                      color={
                        pr.status === 'merged' ? 'purple' : pr.status === 'draft' ? 'grey' : 'green'
                      }
                    >
                      {pr.status}
                    </Label>
                  </div>
                  <div className="lc-meta">
                    {pr.head} → {pr.base} · {pr.updatedAt}
                  </div>
                </div>
              ))}
            </div>
            <div className="repo-changes-diff">
              {selectedPr ? (
                <div className="list-card">
                  <div className="lc-title">
                    #{selectedPr.number} {selectedPr.title}
                  </div>
                  <div className="lc-meta">
                    {selectedPr.head} → {selectedPr.base} · review: {selectedPr.reviewStatus}
                  </div>
                  <p style={{ fontSize: 13 }}>{selectedPr.body}</p>
                  <div className="section-label">Checks</div>
                  {selectedPr.checks.length === 0 && <div className="lc-meta">No checks</div>}
                  {selectedPr.checks.map((c) => (
                    <div key={c.name} className="lc-meta">
                      {c.name}: {c.status}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="code-empty-msg">Select a pull request</div>
              )}
            </div>
          </div>
        )}

        {sub === 'issues' && (
          <div className="repo-changes-layout">
            <div className="repo-changes-list">
              <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                <Button variant="primary" size="sm" onClick={() => setIssueOpen(true)}>
                  New issue
                </Button>
                {(['open', 'closed', 'all'] as const).map((f) => (
                  <Button
                    key={f}
                    size="sm"
                    variant={issueFilter === f ? 'primary' : 'secondary'}
                    onClick={() => setIssueFilter(f)}
                  >
                    {f}
                  </Button>
                ))}
              </div>
              {issues.length === 0 ? (
                <EmptySplash title="No issues" body="Create an issue for this demo repository." />
              ) : (
                issues.map((iss) => (
                  <div
                    key={iss.id}
                    className="list-card"
                    style={{
                      cursor: 'pointer',
                      outline:
                        selectedIssue?.id === iss.id
                          ? '2px solid var(--pf-t--global--border--color--brand--default)'
                          : undefined,
                    }}
                    onClick={() => {
                      setSelectedIssue(iss)
                      setEditBody(iss.body)
                    }}
                  >
                    <div className="lc-row">
                      <div className="lc-title">
                        #{iss.number} {iss.title}
                      </div>
                      <Label color={iss.status === 'open' ? 'green' : 'grey'}>{iss.status}</Label>
                    </div>
                    <div className="lc-meta">
                      {iss.labels.join(', ')} · {iss.updatedAt}
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="repo-changes-diff">
              {selectedIssue ? (
                <div className="issue-card list-card">
                  <h4 style={{ marginTop: 0 }}>
                    #{selectedIssue.number} {selectedIssue.title}
                  </h4>
                  <div className="issue-meta">
                    {selectedIssue.status} · {selectedIssue.labels.join(', ')} · {selectedIssue.author} ·{' '}
                    {selectedIssue.updatedAt}
                  </div>
                  <TextArea
                    value={editBody}
                    onChange={(_e, v) => setEditBody(v)}
                    rows={4}
                    aria-label="Issue body"
                    style={{ marginTop: 8 }}
                  />
                  <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => {
                        updateIssue(projectId, selectedIssue.id, { body: editBody })
                        setSelectedIssue({ ...selectedIssue, body: editBody })
                        pushToast('Issue updated', { kind: 'success' })
                      }}
                    >
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        const status = selectedIssue.status === 'open' ? 'closed' : 'open'
                        updateIssue(projectId, selectedIssue.id, { status })
                        setSelectedIssue({ ...selectedIssue, status })
                        pushToast(status === 'closed' ? 'Issue closed' : 'Issue reopened', { kind: 'info' })
                      }}
                    >
                      {selectedIssue.status === 'open' ? 'Close' : 'Reopen'}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => {
                        deleteIssue(projectId, selectedIssue.id)
                        setSelectedIssue(null)
                        pushToast('Issue deleted', { kind: 'warning' })
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                  <div className="section-label">Comments</div>
                  {selectedIssue.comments.map((c) => (
                    <div className="issue-comment" key={c.id}>
                      <strong>{c.author}</strong>: {c.body}
                    </div>
                  ))}
                  {selectedIssue.comments.length === 0 && <div className="lc-meta">No comments</div>}
                </div>
              ) : (
                <div className="code-empty-msg">Select an issue</div>
              )}
            </div>
          </div>
        )}

        {sub === 'graph' && (
          <div className="git-graph">
            <p className="lc-meta" style={{ marginTop: 0 }}>
              Branch graph (demo) — click a commit to open History detail.
            </p>
            {graphLanes.map(({ commit: c, lane }) => (
              <div
                key={c.id}
                className="git-graph-row"
                style={{ cursor: 'pointer' }}
                onClick={() => {
                  setSelectedCommitId(c.id)
                  setSub('history')
                }}
              >
                <div className="git-graph-lanes" style={{ width: 24 + lane * 18 }}>
                  {Array.from({ length: lane + 1 }).map((_, i) => (
                    <span
                      key={i}
                      className="git-graph-line"
                      style={{ left: 8 + i * 18 }}
                    />
                  ))}
                  <span
                    className={`git-graph-dot ${c.isHead ? 'is-head' : ''}`}
                    style={{ left: 8 + lane * 18 }}
                  />
                </div>
                <div>
                  {c.branchLabels.map((b) => (
                    <span key={b} className="git-branch-tag">
                      {b}
                    </span>
                  ))}
                  <span style={{ fontFamily: 'var(--mono)', marginRight: 8 }}>{c.shortHash}</span>
                  {c.message}
                  <div className="lc-meta">
                    {c.author} · {c.when}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <CreateResourceModal
        isOpen={issueOpen}
        title="Create issue"
        onClose={() => setIssueOpen(false)}
        onSubmit={() => {
          if (!issueTitle.trim()) return
          createIssue(projectId, {
            title: issueTitle.trim(),
            body: issueBody,
            labels: issueLabels
              .split(',')
              .map((l) => l.trim())
              .filter(Boolean),
          })
          pushToast('Issue created', { kind: 'success' })
          setIssueTitle('')
          setIssueBody('')
          setIssueOpen(false)
        }}
        isSubmitDisabled={!issueTitle.trim()}
      >
        <FormGroup label="Title" isRequired fieldId="iss-title">
          <TextInput id="iss-title" value={issueTitle} onChange={(_e, v) => setIssueTitle(v)} />
        </FormGroup>
        <FormGroup label="Body" fieldId="iss-body">
          <TextArea id="iss-body" value={issueBody} onChange={(_e, v) => setIssueBody(v)} rows={4} />
        </FormGroup>
        <FormGroup label="Labels (comma-separated)" fieldId="iss-labels">
          <TextInput id="iss-labels" value={issueLabels} onChange={(_e, v) => setIssueLabels(v)} />
        </FormGroup>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={prOpen}
        title="Create pull request"
        onClose={() => setPrOpen(false)}
        onSubmit={() => {
          if (!prTitle.trim()) return
          createPr(projectId, {
            title: prTitle.trim(),
            body: prBody,
            base: prBase,
            head: prHead,
          })
          pushToast('Pull request created', { kind: 'success' })
          setPrTitle('')
          setPrBody('')
          setPrOpen(false)
        }}
        isSubmitDisabled={!prTitle.trim()}
      >
        <FormGroup label="Title" isRequired fieldId="pr-title">
          <TextInput id="pr-title" value={prTitle} onChange={(_e, v) => setPrTitle(v)} />
        </FormGroup>
        <FormGroup label="Description" fieldId="pr-body">
          <TextArea id="pr-body" value={prBody} onChange={(_e, v) => setPrBody(v)} rows={3} />
        </FormGroup>
        <FormGroup label="Base" fieldId="pr-base">
          <TextInput id="pr-base" value={prBase} onChange={(_e, v) => setPrBase(v)} />
        </FormGroup>
        <FormGroup label="Head" fieldId="pr-head">
          <TextInput id="pr-head" value={prHead} onChange={(_e, v) => setPrHead(v)} />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
