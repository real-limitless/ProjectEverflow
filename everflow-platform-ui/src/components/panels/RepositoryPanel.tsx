import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  MenuToggle,
  Select,
  SelectList,
  SelectOption,
  Spinner,
  TextArea,
  TextInput,
  Tabs,
  Tab,
  TabTitleText,
} from '@patternfly/react-core'
import CodeBranchIcon from '@patternfly/react-icons/dist/esm/icons/code-branch-icon'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject, updateProjectInCatalog } from '@/data/projects'
import { basename } from '@/lib/fileTree'
import { pushToast } from '@/lib/studioToast'
import {
  catalogReposToWorkspace,
  checkoutBranch,
  discoverWorkspaceRepos,
  listBranches,
  loadCommitFiles,
  loadGitChanges,
  loadGitHistory,
  type BranchListItem,
  type WorkspaceRepo,
} from '@/lib/workspaceGit'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { GitFileChange } from '@/types/project'
import type { GitCommit, IssueStatus, PullRequest, RepoIssue } from '@/types/studio'

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

function matchesRepoId(itemRepoId: string | undefined, activeRepoId: string, primaryId: string): boolean {
  if (!activeRepoId) return true
  // Untagged items belong to the primary/active-at-seed repo
  if (!itemRepoId) return activeRepoId === primaryId
  return itemRepoId === activeRepoId
}

export function RepositoryPanel() {
  const [sub, setSub] = useState<'changes' | 'history' | 'prs' | 'issues' | 'graph'>('changes')
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const activeRepoByProject = usePlaygroundStore((s) => s.activeRepoByProject)
  const setActiveRepo = usePlaygroundStore((s) => s.setActiveRepo)
  const getActiveRepoId = usePlaygroundStore((s) => s.getActiveRepoId)

  void catalogVersion
  void activeRepoByProject

  const projectId = currentProjectId || 'default'
  const p = getProject(currentProjectId)
  const catalogRepos = p?.repos || []
  const activeRepoId = getActiveRepoId(currentProjectId)
  const primaryRepoId = catalogRepos.find((r) => r.active)?.id || catalogRepos[0]?.id || activeRepoId

  const fromApi = Boolean(p?.fromApi)
  const sandboxRunning = p?.sandboxStatus === 'running'
  const liveMode = fromApi && sandboxRunning

  const studio = useProjectStudio(projectId)
  const createIssue = useStudioDemoStore((s) => s.createIssue)
  const updateIssue = useStudioDemoStore((s) => s.updateIssue)
  const deleteIssue = useStudioDemoStore((s) => s.deleteIssue)
  const createPr = useStudioDemoStore((s) => s.createPr)

  const [workspaceRepos, setWorkspaceRepos] = useState<WorkspaceRepo[]>(() =>
    catalogReposToWorkspace(catalogRepos),
  )
  const [discovering, setDiscovering] = useState(false)
  const [liveChanges, setLiveChanges] = useState<GitFileChange[] | null>(null)
  const [liveCommits, setLiveCommits] = useState<GitCommit[] | null>(null)
  const [gitLoading, setGitLoading] = useState(false)
  const [gitError, setGitError] = useState<string | null>(null)
  const [liveBranch, setLiveBranch] = useState<string | null>(null)
  const [branchOpen, setBranchOpen] = useState(false)
  const [branches, setBranches] = useState<BranchListItem[]>([])
  const [branchSwitching, setBranchSwitching] = useState(false)
  /** Demo-mode selected branch override */
  const [demoBranch, setDemoBranch] = useState<string | null>(null)

  const [selectedPath, setSelectedPath] = useState('')
  const [staged, setStaged] = useState<Record<string, boolean>>({})
  const [issueFilter, setIssueFilter] = useState<'all' | IssueStatus>('open')
  const [selectedIssue, setSelectedIssue] = useState<RepoIssue | null>(null)
  const [selectedPr, setSelectedPr] = useState<PullRequest | null>(null)
  const [selectedCommitId, setSelectedCommitId] = useState('')

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

  // Selector list: live discovery when sandbox running, else catalog
  const repoOptions: WorkspaceRepo[] = useMemo(() => {
    if (liveMode && workspaceRepos.length) return workspaceRepos
    return catalogReposToWorkspace(catalogRepos)
    // catalogVersion tracks catalog.repos mutations
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveMode, workspaceRepos, catalogVersion, currentProjectId])

  const selectedRepo: WorkspaceRepo = useMemo(() => {
    return (
      repoOptions.find((r) => r.id === activeRepoId) ||
      repoOptions.find((r) => r.path === activeRepoId) ||
      repoOptions[0] || {
        id: 'main',
        label: 'workspace',
        path: '.',
        hasGit: false,
      }
    )
  }, [repoOptions, activeRepoId])

  // Keep store selection valid when options change
  useEffect(() => {
    if (!currentProjectId || repoOptions.length === 0) return
    if (!repoOptions.some((r) => r.id === activeRepoId)) {
      setActiveRepo(repoOptions[0].id, currentProjectId)
    }
  }, [currentProjectId, repoOptions, activeRepoId, setActiveRepo])

  // Reset selection when repo changes
  useEffect(() => {
    setSelectedPath('')
    setSelectedIssue(null)
    setSelectedPr(null)
    setSelectedCommitId('')
    setStaged({})
    setLiveChanges(null)
    setLiveCommits(null)
    setGitError(null)
    setDemoBranch(null)
    setBranches([])
    setBranchOpen(false)
  }, [selectedRepo.id, selectedRepo.path])

  const refreshDiscovery = useCallback(async () => {
    const catalog = getProject(currentProjectId)?.repos || []
    if (!liveMode || !currentProjectId) {
      setWorkspaceRepos(catalogReposToWorkspace(catalog))
      return
    }
    setDiscovering(true)
    try {
      const found = await discoverWorkspaceRepos(currentProjectId, catalog)
      setWorkspaceRepos(found)
    } catch (e) {
      setWorkspaceRepos(catalogReposToWorkspace(catalog))
      setGitError(e instanceof Error ? e.message : 'Failed to discover repositories')
    } finally {
      setDiscovering(false)
    }
  }, [liveMode, currentProjectId, catalogVersion])

  useEffect(() => {
    void refreshDiscovery()
  }, [refreshDiscovery])

  const refreshGit = useCallback(async () => {
    if (!liveMode || !currentProjectId) {
      setLiveChanges(null)
      setLiveCommits(null)
      setLiveBranch(null)
      setGitError(null)
      return
    }
    if (!selectedRepo.hasGit) {
      setLiveChanges([])
      setLiveCommits([])
      setLiveBranch(null)
      setGitError(null)
      return
    }
    setGitLoading(true)
    setGitError(null)
    try {
      const [changes, commits] = await Promise.all([
        loadGitChanges(currentProjectId, selectedRepo.path),
        loadGitHistory(currentProjectId, selectedRepo.path),
      ])
      setLiveChanges(changes)
      setLiveCommits(commits)
      setLiveBranch(selectedRepo.branch || null)

      // Cache working-tree changes for Code panel gutters (avoid catalogVersion churn loops)
      updateProjectInCatalog(currentProjectId, { gitChanges: changes })

      if (commits[0]) {
        setSelectedCommitId((prev) => prev || commits[0].id)
      }
      if (changes[0]) {
        setSelectedPath((prev) => prev || changes[0].path)
      }
    } catch (e) {
      setLiveChanges(null)
      setLiveCommits(null)
      setGitError(e instanceof Error ? e.message : 'Failed to load git data')
    } finally {
      setGitLoading(false)
    }
  }, [liveMode, currentProjectId, selectedRepo.hasGit, selectedRepo.path, selectedRepo.branch])

  useEffect(() => {
    void refreshGit()
  }, [refreshGit])

  const loadBranchList = useCallback(async () => {
    if (liveMode && currentProjectId && selectedRepo.hasGit) {
      try {
        const list = await listBranches(currentProjectId, selectedRepo.path)
        setBranches(list)
      } catch {
        setBranches([])
      }
      return
    }
    // Demo: branches from commit labels + catalog
    const names = new Set<string>()
    const catalogBranch =
      catalogRepos.find((r) => r.id === selectedRepo.id)?.branch ||
      selectedRepo.branch ||
      'main'
    if (catalogBranch) names.add(catalogBranch)
    names.add('main')
    for (const c of studio.commits) {
      if (!matchesRepoId(c.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id)) continue
      for (const b of c.branchLabels) {
        if (!b || b === 'HEAD' || b.startsWith('HEAD')) continue
        names.add(b)
      }
    }
    setBranches([...names].filter(Boolean).sort().map((name) => ({ name })))
  }, [
    liveMode,
    currentProjectId,
    selectedRepo.hasGit,
    selectedRepo.path,
    selectedRepo.id,
    selectedRepo.branch,
    catalogRepos,
    studio.commits,
    primaryRepoId,
  ])

  useEffect(() => {
    void loadBranchList()
  }, [loadBranchList])

  // Demo / fallback data scoped by repo
  const seedChanges = useMemo(() => {
    const all = p?.gitChanges || []
    if (catalogRepos.length <= 1) return all
    const hint = selectedRepo.path === '.' ? '' : selectedRepo.path
    if (!hint) return all
    const filtered = all.filter(
      (c) => c.path === hint || c.path.startsWith(`${hint}/`) || c.path.startsWith(`${selectedRepo.id}/`),
    )
    return filtered.length ? filtered : all
  }, [p?.gitChanges, catalogRepos.length, selectedRepo.path, selectedRepo.id])

  const changes: GitFileChange[] = liveMode && liveChanges !== null ? liveChanges : seedChanges

  const branchLabel =
    liveBranch ||
    demoBranch ||
    selectedRepo.branch ||
    catalogRepos.find((r) => r.id === selectedRepo.id)?.branch ||
    'main'

  const demoCommits = useMemo(() => {
    const scoped = studio.commits.filter((c) =>
      matchesRepoId(c.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id),
    )
    if (!demoBranch) return scoped
    const filtered = scoped.filter(
      (c) =>
        c.branchLabels.includes(demoBranch) ||
        c.branchLabels.some((b) => b === demoBranch || b.endsWith(`/${demoBranch}`)),
    )
    // Keep graph useful: if filter empties, fall back to all scoped
    return filtered.length ? filtered : scoped
  }, [studio.commits, selectedRepo.id, primaryRepoId, demoBranch])
  const commits: GitCommit[] =
    liveMode && liveCommits !== null ? liveCommits : demoCommits

  const issues = useMemo(
    () =>
      studio.issues.filter(
        (i) =>
          (issueFilter === 'all' || i.status === issueFilter) &&
          matchesRepoId(i.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id),
      ),
    [studio.issues, issueFilter, selectedRepo.id, primaryRepoId],
  )
  const pullRequests = useMemo(
    () =>
      studio.pullRequests.filter((pr) =>
        matchesRepoId(pr.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id),
      ),
    [studio.pullRequests, selectedRepo.id, primaryRepoId],
  )

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
  const selectedCommit = commits.find((c) => c.id === selectedCommitId) ?? commits[0]

  // Lazy-load files for a live commit
  useEffect(() => {
    if (!liveMode || !currentProjectId || !selectedCommit || selectedCommit.files.length > 0) return
    if (!selectedRepo.hasGit) return
    let cancelled = false
    void loadCommitFiles(currentProjectId, selectedRepo.path, selectedCommit.hash).then((files) => {
      if (cancelled || !files.length) return
      setLiveCommits((prev) =>
        (prev || []).map((c) => (c.id === selectedCommit.id ? { ...c, files } : c)),
      )
    })
    return () => {
      cancelled = true
    }
  }, [
    liveMode,
    currentProjectId,
    selectedCommit?.id,
    selectedCommit?.hash,
    selectedCommit?.files.length,
    selectedRepo.hasGit,
    selectedRepo.path,
  ])

  const graphLanes = useMemo(() => {
    const branchLane = new Map<string, number>()
    let next = 0
    return commits.map((c) => {
      const label = c.branchLabels.find((b) => b !== 'HEAD') || c.branchLabels[0] || 'main'
      if (!branchLane.has(label)) branchLane.set(label, next++)
      return { commit: c, lane: branchLane.get(label) ?? 0 }
    })
  }, [commits])

  const persistBranchOnCatalog = (branch: string) => {
    if (!currentProjectId || !p) return
    const repos = (p.repos || []).map((r) =>
      r.id === selectedRepo.id ? { ...r, branch } : r,
    )
    if (repos.some((r) => r.id === selectedRepo.id)) {
      updateProjectInCatalog(currentProjectId, { repos })
      usePlaygroundStore.setState({
        catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
      })
    }
  }

  const onBranchSelect = async (branch: string) => {
    setBranchOpen(false)
    if (!branch || branch === branchLabel) return

    if (liveMode && currentProjectId && selectedRepo.hasGit) {
      setBranchSwitching(true)
      setGitError(null)
      try {
        const result = await checkoutBranch(currentProjectId, selectedRepo.path, branch)
        if (!result.ok) {
          setGitError(result.error)
          pushToast(result.error.slice(0, 120), { kind: 'danger' })
          return
        }
        setLiveBranch(result.branch)
        persistBranchOnCatalog(result.branch)
        pushToast(`Checked out ${result.branch}`, { kind: 'success' })
        await refreshGit()
        await loadBranchList()
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Branch switch failed'
        setGitError(msg)
        pushToast(msg, { kind: 'danger' })
      } finally {
        setBranchSwitching(false)
      }
      return
    }

    setDemoBranch(branch)
    persistBranchOnCatalog(branch)
  }

  const onRepoSelect = (repoId: string) => {
    if (!currentProjectId) return
    // If selection is a discovered ws-* id not in catalog, still store it
    setActiveRepo(repoId, currentProjectId)
    // Ensure catalog has an entry so strip can show it when possible
    if (p && !p.repos.some((r) => r.id === repoId)) {
      const wr = repoOptions.find((r) => r.id === repoId)
      if (wr) {
        updateProjectInCatalog(currentProjectId, {
          repos: [
            ...p.repos.map((r) => ({ ...r, active: false })),
            {
              id: wr.id,
              label: wr.label,
              active: true,
              branch: wr.branch,
              url: wr.url,
              provider: wr.provider || 'none',
              localPath: wr.path,
            },
          ],
        })
        usePlaygroundStore.setState({
          catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
          activeRepoByProject: {
            ...usePlaygroundStore.getState().activeRepoByProject,
            [currentProjectId]: wr.id,
          },
        })
      }
    }
  }

  const sourceHint = liveMode
    ? selectedRepo.hasGit
      ? `Workspace · ${selectedRepo.path === '.' ? '/workspace' : `/workspace/${selectedRepo.path}`}`
      : 'No git repository at this path'
    : 'Demo data (sandbox not live)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="repo-toolbar">
        <div className="repo-toolbar-left">
          {repoOptions.length > 1 ? (
            <FormSelect
              id="repo-select"
              className="repo-select"
              value={selectedRepo.id}
              onChange={(_e, v) => onRepoSelect(v)}
              aria-label="Select repository"
              isDisabled={discovering}
            >
              {repoOptions.map((r) => (
                <FormSelectOption
                  key={r.id}
                  value={r.id}
                  label={r.hasGit || !liveMode ? r.label : `${r.label} (no git)`}
                />
              ))}
            </FormSelect>
          ) : (
            <span className="repo-toolbar-label" title={selectedRepo.path}>
              {selectedRepo.label}
            </span>
          )}
          <Select
            id="repo-branch-select"
            isOpen={branchOpen}
            selected={branchLabel}
            onSelect={(_e, value) => {
              void onBranchSelect(String(value))
            }}
            onOpenChange={(open) => {
              setBranchOpen(open)
              if (open) void loadBranchList()
            }}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                className="repo-branch-toggle"
                onClick={() => setBranchOpen(!branchOpen)}
                isExpanded={branchOpen}
                isDisabled={branchSwitching || (liveMode && !selectedRepo.hasGit && branches.length === 0)}
                icon={<CodeBranchIcon />}
                aria-label={`Branch ${branchLabel}`}
              >
                <span className="repo-branch-toggle-text">{branchLabel || '—'}</span>
              </MenuToggle>
            )}
          >
            <SelectList>
              {branches.length === 0 && (
                <SelectOption isDisabled value="">
                  {gitLoading || branchSwitching ? 'Loading branches…' : 'No branches'}
                </SelectOption>
              )}
              {branches.map((b) => (
                <SelectOption
                  key={b.name}
                  value={b.name}
                  description={b.remote ? 'remote' : undefined}
                  isSelected={b.name === branchLabel}
                >
                  {b.name}
                </SelectOption>
              ))}
            </SelectList>
          </Select>
          <Button
            variant="plain"
            size="sm"
            className={`repo-refresh-btn${gitLoading || discovering || branchSwitching ? ' is-spinning' : ''}`}
            icon={<SyncAltIcon />}
            aria-label="Refresh repository"
            title="Refresh"
            isDisabled={gitLoading || discovering || branchSwitching}
            onClick={() => {
              void refreshDiscovery()
                .then(() => refreshGit())
                .then(() => loadBranchList())
            }}
          />
          {(gitLoading || discovering || branchSwitching) && (
            <Spinner size="sm" aria-label="Loading git" />
          )}
        </div>
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
      <div className="repo-source-meta">{sourceHint}</div>
      {gitError && (
        <div className="repo-git-error" role="alert">
          {gitError}
        </div>
      )}
      <div className="repo-body" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
        {sub === 'changes' && (
          liveMode && !selectedRepo.hasGit ? (
            <EmptySplash
              title="Not a git repository"
              body={`No .git found for ${selectedRepo.label}. Clone or init a repo under the workspace path, then Refresh.`}
            />
          ) : changes.length === 0 ? (
            <EmptySplash title="Clean working tree" body="No working-tree changes in this repository." />
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
          commits.length === 0 ? (
            <EmptySplash
              title="No commits"
              body={
                liveMode && !selectedRepo.hasGit
                  ? 'Not a git repository at this path.'
                  : 'No history for this repository yet.'
              }
            />
          ) : (
            <div className="repo-changes-layout">
              <div className="repo-changes-list">
                {commits.map((c) => (
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
                    {selectedCommit.files.length === 0 && (
                      <div className="lc-meta">{liveMode ? 'Loading…' : 'No files listed'}</div>
                    )}
                    {selectedCommit.files.map((f) => (
                      <div key={f} className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                        {f}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        )}

        {sub === 'prs' && (
          <div className="repo-changes-layout">
            <div className="repo-changes-list">
              <Button variant="primary" size="sm" style={{ marginBottom: 8 }} onClick={() => setPrOpen(true)}>
                Create pull request
              </Button>
              {pullRequests.length === 0 ? (
                <EmptySplash title="No pull requests" body="No PRs for this repository yet." />
              ) : (
                pullRequests.map((pr) => (
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
                ))
              )}
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
                <EmptySplash title="No issues" body="No issues for this repository." />
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
          commits.length === 0 ? (
            <EmptySplash title="No graph" body="No commits to visualize for this repository." />
          ) : (
            <div className="git-graph">
              <p className="lc-meta" style={{ marginTop: 0 }}>
                Branch graph{liveMode ? ' (workspace)' : ' (demo)'} — click a commit to open History.
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
                      <span key={i} className="git-graph-line" style={{ left: 8 + i * 18 }} />
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
          )
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
            repoId: selectedRepo.id,
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
            repoId: selectedRepo.id,
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
