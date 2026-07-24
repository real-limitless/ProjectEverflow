import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { gitPull, gitPush } from '@/lib/api'
import { pushToast } from '@/lib/studioToast'
import {
  approveWorktree,
  catalogReposToWorkspace,
  checkoutBranch,
  discardWorktree,
  discoverWorkspaceRepos,
  isEverflowWorktreePath,
  getCurrentBranch,
  listBranches,
  listWorktrees,
  loadCommitFiles,
  loadGitChanges,
  loadGitHistory,
  readWorktreeIndex,
  type BranchListItem,
  type ConversationWorktreeMeta,
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

/** Demo seed issue ids (iss-42, iss-sec-*) vs user-created uid() ids (iss-<ts>-<rand>). */
function isSeedIssueId(id: string): boolean {
  return /^iss-\d+$/.test(id) || id.startsWith('iss-sec-')
}

/** Demo seed PR ids (pr-12, pr-sec-*) vs user-created uid() ids. */
function isSeedPrId(id: string): boolean {
  return /^pr-\d+$/.test(id) || id.startsWith('pr-sec-')
}

export function RepositoryPanel() {
  const [sub, setSub] = useState<'changes' | 'history' | 'prs' | 'issues' | 'graph'>('changes')
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const activeRepoByProject = usePlaygroundStore((s) => s.activeRepoByProject)
  const setActiveRepo = usePlaygroundStore((s) => s.setActiveRepo)
  const getActiveRepoId = usePlaygroundStore((s) => s.getActiveRepoId)
  const repoViewPathByProject = usePlaygroundStore((s) => s.repoViewPathByProject)
  const setRepoViewPath = usePlaygroundStore((s) => s.setRepoViewPath)
  const projectChats = usePlaygroundStore((s) => s.projectChats)
  const patchConversationWorktree = usePlaygroundStore((s) => s.patchConversationWorktree)

  void catalogVersion
  void activeRepoByProject

  const projectId = currentProjectId || 'default'
  const p = getProject(currentProjectId)
  const fromApi = Boolean(p?.fromApi)
  const catalogRepos = useMemo(() => {
    const all = p?.repos || []
    if (!fromApi) return all
    // Hide provider:none placeholders left over from older creates / local cache
    return all.filter(
      (r) =>
        Boolean(r.url?.trim()) ||
        (r.provider && r.provider !== 'none') ||
        Boolean(r.localPath && r.localPath !== '.'),
    )
  }, [p?.repos, fromApi])
  const activeRepoId = getActiveRepoId(currentProjectId)
  const primaryRepoId = catalogRepos.find((r) => r.active)?.id || catalogRepos[0]?.id || activeRepoId

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
  const workspaceReposRef = useRef(workspaceRepos)
  workspaceReposRef.current = workspaceRepos
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
  const [linkedWorktrees, setLinkedWorktrees] = useState<
    Array<ConversationWorktreeMeta & { chatTitle?: string; dirtyHint?: number }>
  >([])
  const [worktreeBusy, setWorktreeBusy] = useState(false)
  const [remoteBusy, setRemoteBusy] = useState(false)

  const viewPathOverride =
    (currentProjectId && repoViewPathByProject[currentProjectId]) || null

  // Selector list: live discovery when sandbox running, else catalog.
  // Live mode never surfaces catalog ghosts without git (e.g. "test (no git)").
  const repoOptions: WorkspaceRepo[] = useMemo(() => {
    if (liveMode && workspaceRepos.length) {
      const withGit = workspaceRepos.filter((r) => r.hasGit)
      // Live discovery with no git roots: still empty for API projects with no catalog remotes
      if (withGit.length > 0) return withGit
      if (fromApi && catalogRepos.length === 0) return []
      return workspaceRepos.slice(0, 1)
    }
    return catalogReposToWorkspace(catalogRepos)
    // catalogVersion tracks catalog.repos mutations
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveMode, fromApi, workspaceRepos, catalogRepos, catalogVersion, currentProjectId])

  const hasAttachedRepo = repoOptions.length > 0

  const selectedRepo: WorkspaceRepo = useMemo(() => {
    return (
      repoOptions.find((r) => r.id === activeRepoId) ||
      repoOptions.find((r) => r.path === activeRepoId) ||
      repoOptions[0] || {
        id: 'main',
        label: fromApi ? 'No repository' : 'workspace',
        path: '.',
        hasGit: false,
      }
    )
  }, [repoOptions, activeRepoId, fromApi])

  const effectiveGitPath = useMemo(() => {
    if (viewPathOverride && isEverflowWorktreePath(viewPathOverride)) {
      return viewPathOverride
    }
    return selectedRepo.path
  }, [viewPathOverride, selectedRepo.path])

  const viewingWorktree = isEverflowWorktreePath(effectiveGitPath)

  const activeLinkedWorktree = useMemo(() => {
    const fromList = linkedWorktrees.find(
      (w) => w.path === effectiveGitPath && w.status === 'active',
    )
    if (fromList) return fromList
    if (!viewingWorktree || !currentProjectId) return undefined
    const chat = (projectChats[currentProjectId] || []).find(
      (c) => c.worktree?.path === effectiveGitPath && c.worktree.status === 'active',
    )
    if (!chat?.worktree) return undefined
    return {
      sessionId: chat.id,
      repoId: chat.worktree.repoId,
      parentPath: chat.worktree.parentPath,
      path: chat.worktree.path,
      branch: chat.worktree.branch,
      status: 'active' as const,
      chatTitle: chat.title,
    }
  }, [
    linkedWorktrees,
    effectiveGitPath,
    viewingWorktree,
    currentProjectId,
    projectChats,
  ])

  // Keep store selection valid when options change
  useEffect(() => {
    if (!currentProjectId || repoOptions.length === 0) return
    if (!repoOptions.some((r) => r.id === activeRepoId)) {
      setActiveRepo(repoOptions[0].id, currentProjectId)
    }
  }, [currentProjectId, repoOptions, activeRepoId, setActiveRepo])

  // Reset selection when repo or view path changes
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
  }, [selectedRepo.id, selectedRepo.path, effectiveGitPath])

  const refreshDiscovery = useCallback(async () => {
    let catalog = getProject(currentProjectId)?.repos || []
    if (!liveMode || !currentProjectId) {
      setWorkspaceRepos(catalogReposToWorkspace(catalog))
      return
    }
    setDiscovering(true)
    try {
      // Ensure any catalog URLs missing from the workspace are cloned first
      const { ensureReposCloned, isCloneableUrl } = await import('@/lib/workspaceRepos')
      const needsClone = catalog.some(
        (r) =>
          isCloneableUrl(r.url) && r.cloneStatus !== 'ready' && r.cloneStatus !== 'skipped',
      )
      if (needsClone) {
        const result = await ensureReposCloned(currentProjectId, catalog)
        updateProjectInCatalog(currentProjectId, { repos: result.repos })
        usePlaygroundStore.setState({
          catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
        })
        catalog = result.repos
        if (result.failed > 0) {
          const first = result.repos.find((r) => r.cloneStatus === 'error')
          setGitError(first?.cloneError || 'Failed to clone one or more repositories')
        }
      }
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

  // Re-discover shortly after boot — provision can report running before clone/seed finishes.
  // Keep this light: full discovery is expensive (git probes) and can stall chat.
  useEffect(() => {
    if (!liveMode || !currentProjectId) return
    let cancelled = false
    let attempts = 0
    const maxAttempts = 8
    const id = window.setInterval(() => {
      if (cancelled) return
      attempts += 1
      if (workspaceReposRef.current.some((r) => r.hasGit) || attempts >= maxAttempts) {
        window.clearInterval(id)
        return
      }
      void refreshDiscovery()
    }, 6000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [liveMode, currentProjectId, refreshDiscovery])

  const refreshLinkedWorktrees = useCallback(async () => {
    if (!liveMode || !currentProjectId || !selectedRepo.hasGit) {
      setLinkedWorktrees([])
      return
    }
    try {
      const [listed, index] = await Promise.all([
        listWorktrees(currentProjectId, selectedRepo.path).catch(() => []),
        readWorktreeIndex(currentProjectId).catch(() => ({ entries: [] as ConversationWorktreeMeta[] })),
      ])
      const chats = projectChats[currentProjectId] || []
      const byPath = new Map<string, ConversationWorktreeMeta & { chatTitle?: string }>()

      for (const e of index.entries) {
        if (e.status !== 'active') continue
        if (e.parentPath !== selectedRepo.path && e.repoId !== selectedRepo.id) continue
        const chat = chats.find((c) => c.id === e.sessionId)
        byPath.set(e.path, { ...e, chatTitle: chat?.title })
      }
      for (const wt of listed) {
        if (!isEverflowWorktreePath(wt.path)) continue
        if (wt.path === selectedRepo.path) continue
        const existing = byPath.get(wt.path)
        if (existing) {
          if (wt.branch) existing.branch = wt.branch
          continue
        }
        const chat = chats.find((c) => c.worktree?.path === wt.path)
        byPath.set(wt.path, {
          sessionId: chat?.id || wt.path,
          repoId: selectedRepo.id,
          parentPath: selectedRepo.path,
          path: wt.path,
          branch: wt.branch || chat?.worktree?.branch || 'detached',
          status: 'active',
          chatTitle: chat?.title,
        })
      }

      const rows = Array.from(byPath.values())
      // Best-effort dirty counts
      const withDirty = await Promise.all(
        rows.map(async (row) => {
          try {
            const changes = await loadGitChanges(currentProjectId, row.path, {
              withDiffs: false,
            })
            return { ...row, dirtyHint: changes.length }
          } catch {
            return { ...row, dirtyHint: undefined }
          }
        }),
      )
      setLinkedWorktrees(withDirty)
    } catch {
      setLinkedWorktrees([])
    }
  }, [
    liveMode,
    currentProjectId,
    selectedRepo.hasGit,
    selectedRepo.path,
    selectedRepo.id,
    projectChats,
  ])

  useEffect(() => {
    void refreshLinkedWorktrees()
  }, [refreshLinkedWorktrees])

  const refreshGit = useCallback(async () => {
    if (!liveMode || !currentProjectId) {
      setLiveChanges(null)
      setLiveCommits(null)
      setLiveBranch(null)
      setGitError(null)
      return
    }
    if (!selectedRepo.hasGit && !viewingWorktree) {
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
        loadGitChanges(currentProjectId, effectiveGitPath),
        loadGitHistory(currentProjectId, effectiveGitPath),
      ])
      setLiveChanges(changes)
      setLiveCommits(commits)
      const branchRes = await getCurrentBranch(currentProjectId, effectiveGitPath)
      setLiveBranch(branchRes || selectedRepo.branch || null)

      // Cache working-tree changes for Code panel gutters only for main checkout
      if (!viewingWorktree) {
        updateProjectInCatalog(currentProjectId, { gitChanges: changes })
      }

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
  }, [
    liveMode,
    currentProjectId,
    selectedRepo.hasGit,
    selectedRepo.branch,
    effectiveGitPath,
    viewingWorktree,
  ])

  useEffect(() => {
    void refreshGit()
  }, [refreshGit])

  const loadBranchList = useCallback(async () => {
    if (liveMode && currentProjectId && (selectedRepo.hasGit || viewingWorktree)) {
      try {
        const list = await listBranches(currentProjectId, effectiveGitPath)
        setBranches(list)
      } catch {
        setBranches([])
      }
      return
    }
    // API projects: never invent demo branches (fix/metric-threshold, …).
    if (fromApi) {
      const catalogBranch =
        catalogRepos.find((r) => r.id === selectedRepo.id)?.branch ||
        selectedRepo.branch
      setBranches(catalogBranch ? [{ name: catalogBranch }] : [])
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
    fromApi,
    currentProjectId,
    selectedRepo.hasGit,
    selectedRepo.path,
    selectedRepo.id,
    selectedRepo.branch,
    catalogRepos,
    studio.commits,
    primaryRepoId,
    effectiveGitPath,
    viewingWorktree,
  ])

  useEffect(() => {
    void loadBranchList()
  }, [loadBranchList])

  // Demo / fallback data scoped by repo
  const seedChanges = useMemo(() => {
    if (fromApi) return []
    const all = p?.gitChanges || []
    if (catalogRepos.length <= 1) return all
    const hint = selectedRepo.path === '.' ? '' : selectedRepo.path
    if (!hint) return all
    const filtered = all.filter(
      (c) => c.path === hint || c.path.startsWith(`${hint}/`) || c.path.startsWith(`${selectedRepo.id}/`),
    )
    return filtered.length ? filtered : all
  }, [fromApi, p?.gitChanges, catalogRepos.length, selectedRepo.path, selectedRepo.id])

  const changes: GitFileChange[] = liveMode && liveChanges !== null ? liveChanges : seedChanges

  const branchLabel =
    liveBranch ||
    (!fromApi ? demoBranch : null) ||
    selectedRepo.branch ||
    catalogRepos.find((r) => r.id === selectedRepo.id)?.branch ||
    (fromApi ? (liveBranch || '—') : 'main')

  const demoCommits = useMemo(() => {
    if (fromApi) return []
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
  }, [fromApi, studio.commits, selectedRepo.id, primaryRepoId, demoBranch])
  const commits: GitCommit[] =
    liveMode && liveCommits !== null ? liveCommits : fromApi ? liveCommits || [] : demoCommits

  // Live API projects must not show showcase seed issues/PRs (those exist only for demo mode).
  const issues = useMemo(() => {
    const scoped = studio.issues.filter(
      (i) =>
        (issueFilter === 'all' || i.status === issueFilter) &&
        matchesRepoId(i.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id),
    )
    if (!fromApi) return scoped
    // Seed IDs look like iss-42 / iss-sec-*; user-created use uid() → iss-<ts>-<rand>
    return scoped.filter((i) => !isSeedIssueId(i.id))
  }, [studio.issues, issueFilter, selectedRepo.id, primaryRepoId, fromApi])
  const pullRequests = useMemo(() => {
    const scoped = studio.pullRequests.filter((pr) =>
      matchesRepoId(pr.repoId, selectedRepo.id, primaryRepoId || selectedRepo.id),
    )
    if (!fromApi) return scoped
    return scoped.filter((pr) => !isSeedPrId(pr.id))
  }, [studio.pullRequests, selectedRepo.id, primaryRepoId, fromApi])

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
    if (!selectedRepo.hasGit && !viewingWorktree) return
    let cancelled = false
    void loadCommitFiles(currentProjectId, effectiveGitPath, selectedCommit.hash).then((files) => {
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
    effectiveGitPath,
    viewingWorktree,
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

    if (liveMode && currentProjectId && (selectedRepo.hasGit || viewingWorktree)) {
      setBranchSwitching(true)
      setGitError(null)
      try {
        const result = await checkoutBranch(currentProjectId, effectiveGitPath, branch)
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

  const catalogSelected = (p?.repos || []).find(
    (r) => r.id === selectedRepo.id || r.localPath === selectedRepo.path,
  )
  const cloneHint =
    catalogSelected?.cloneStatus === 'error'
      ? `Clone failed: ${catalogSelected.cloneError?.split('\n')[0] || 'error'}`
      : catalogSelected?.cloneStatus === 'pending' || catalogSelected?.cloneStatus === 'cloning'
        ? 'Cloning repository into workspace…'
        : null

  const sourceHint = liveMode
    ? viewingWorktree
      ? `Worktree · /workspace/${effectiveGitPath}${
          activeLinkedWorktree?.branch ? ` · ${activeLinkedWorktree.branch}` : ''
        }`
      : selectedRepo.hasGit
        ? `Workspace · ${selectedRepo.path === '.' ? '/workspace' : `/workspace/${selectedRepo.path}`}`
        : cloneHint ||
          'No git repository at this path — enter a URL at create time or Connect, then Refresh'
    : 'Demo data (sandbox not live)'

  const onApproveLinkedWorktree = async () => {
    if (!currentProjectId || !activeLinkedWorktree) return
    setWorktreeBusy(true)
    try {
      const res = await approveWorktree(currentProjectId, {
        parentPath: activeLinkedWorktree.parentPath,
        worktreePath: activeLinkedWorktree.path,
        branch: activeLinkedWorktree.branch,
        sessionId: activeLinkedWorktree.sessionId,
      })
      if (!res.ok) {
        pushToast(res.error, { kind: 'danger' })
        return
      }
      patchConversationWorktree(
        currentProjectId,
        activeLinkedWorktree.sessionId,
        {
          repoId: activeLinkedWorktree.repoId,
          parentPath: activeLinkedWorktree.parentPath,
          path: activeLinkedWorktree.path,
          branch: activeLinkedWorktree.branch,
          status: 'applied',
        },
        { useWorktree: false },
      )
      setRepoViewPath(currentProjectId, null)
      pushToast(
        res.parentBranch ? `Merged into ${res.parentBranch}` : 'Worktree approved',
        { kind: 'success' },
      )
      await refreshLinkedWorktrees()
      await refreshGit()
    } finally {
      setWorktreeBusy(false)
    }
  }

  const onDiscardLinkedWorktree = async () => {
    if (!currentProjectId || !activeLinkedWorktree) return
    if (
      !window.confirm(
        `Discard isolated branch ${activeLinkedWorktree.branch}? Changes will be lost.`,
      )
    ) {
      return
    }
    setWorktreeBusy(true)
    try {
      const res = await discardWorktree(currentProjectId, {
        parentPath: activeLinkedWorktree.parentPath,
        worktreePath: activeLinkedWorktree.path,
        branch: activeLinkedWorktree.branch,
        sessionId: activeLinkedWorktree.sessionId,
      })
      if (!res.ok) {
        pushToast(res.error, { kind: 'danger' })
        return
      }
      patchConversationWorktree(
        currentProjectId,
        activeLinkedWorktree.sessionId,
        {
          repoId: activeLinkedWorktree.repoId,
          parentPath: activeLinkedWorktree.parentPath,
          path: activeLinkedWorktree.path,
          branch: activeLinkedWorktree.branch,
          status: 'discarded',
        },
        { useWorktree: false },
      )
      setRepoViewPath(currentProjectId, null)
      pushToast('Worktree discarded', { kind: 'warning' })
      await refreshLinkedWorktrees()
      await refreshGit()
    } finally {
      setWorktreeBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="repo-toolbar">
        <div className="repo-toolbar-left">
          {!hasAttachedRepo ? (
            <span className="repo-toolbar-label" title="No repository attached">
              No repository
            </span>
          ) : repoOptions.length > 1 ? (
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
                  label={r.label}
                />
              ))}
            </FormSelect>
          ) : (
            <span className="repo-toolbar-label" title={selectedRepo.path}>
              {selectedRepo.label}
            </span>
          )}
          {liveMode &&
          hasAttachedRepo &&
          (linkedWorktrees.length > 0 || viewingWorktree) ? (
            <FormSelect
              id="worktree-select"
              className="repo-worktree-select"
              value={viewingWorktree ? effectiveGitPath : '__main__'}
              onChange={(_e, v) => {
                if (!currentProjectId) return
                if (v === '__main__') setRepoViewPath(currentProjectId, null)
                else setRepoViewPath(currentProjectId, v)
              }}
              aria-label="Select checkout or worktree"
            >
              <FormSelectOption
                value="__main__"
                label={`Main · ${selectedRepo.label}`}
              />
              {linkedWorktrees.map((w) => (
                <FormSelectOption
                  key={w.path}
                  value={w.path}
                  label={`${w.branch}${w.chatTitle ? ` · ${w.chatTitle}` : ''}${
                    w.dirtyHint != null ? ` (${w.dirtyHint})` : ''
                  }`}
                />
              ))}
              {viewingWorktree &&
              !linkedWorktrees.some((w) => w.path === effectiveGitPath) ? (
                <FormSelectOption
                  value={effectiveGitPath}
                  label={
                    activeLinkedWorktree?.branch
                      ? `${activeLinkedWorktree.branch} · isolated`
                      : effectiveGitPath
                  }
                />
              ) : null}
            </FormSelect>
          ) : null}
          <Select
            id="repo-branch-select"
            isOpen={branchOpen}
            selected={hasAttachedRepo ? branchLabel : '—'}
            onSelect={(_e, value) => {
              void onBranchSelect(String(value))
            }}
            onOpenChange={(open) => {
              if (!hasAttachedRepo) return
              setBranchOpen(open)
              if (open) void loadBranchList()
            }}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                className="repo-branch-toggle"
                onClick={() => {
                  if (!hasAttachedRepo) return
                  setBranchOpen(!branchOpen)
                }}
                isExpanded={branchOpen}
                isDisabled={
                  !hasAttachedRepo ||
                  branchSwitching ||
                  (liveMode && !selectedRepo.hasGit && branches.length === 0)
                }
                icon={<CodeBranchIcon />}
                aria-label={hasAttachedRepo ? `Branch ${branchLabel}` : 'No branch'}
              >
                <span className="repo-branch-toggle-text">
                  {hasAttachedRepo ? branchLabel || '—' : '—'}
                </span>
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
          {viewingWorktree && activeLinkedWorktree ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                isDisabled={worktreeBusy}
                onClick={() => void onApproveLinkedWorktree()}
              >
                Approve into main
              </Button>
              <Button
                variant="danger"
                size="sm"
                isDisabled={worktreeBusy}
                onClick={() => void onDiscardLinkedWorktree()}
              >
                Discard
              </Button>
            </>
          ) : null}
          {liveMode && hasAttachedRepo && selectedRepo.hasGit && currentProjectId ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                isDisabled={remoteBusy || gitLoading}
                isLoading={remoteBusy}
                onClick={() => {
                  void (async () => {
                    setRemoteBusy(true)
                    try {
                      const res = await gitPull(currentProjectId, {
                        path: effectiveGitPath || selectedRepo.path || '.',
                        branch: branchLabel || undefined,
                      })
                      if (!res.ok) {
                        pushToast(res.stderr || res.stdout || 'Pull failed', { kind: 'danger' })
                      } else {
                        pushToast(
                          res.used_credential ? 'Pulled (using saved token)' : 'Pulled',
                          { kind: 'success' },
                        )
                        await refreshGit()
                      }
                    } catch (e) {
                      pushToast(e instanceof Error ? e.message : 'Pull failed', { kind: 'danger' })
                    } finally {
                      setRemoteBusy(false)
                    }
                  })()
                }}
              >
                Pull
              </Button>
              <Button
                variant="secondary"
                size="sm"
                isDisabled={remoteBusy || gitLoading}
                onClick={() => {
                  void (async () => {
                    setRemoteBusy(true)
                    try {
                      const res = await gitPush(currentProjectId, {
                        path: effectiveGitPath || selectedRepo.path || '.',
                        branch: branchLabel || undefined,
                      })
                      if (!res.ok) {
                        pushToast(res.stderr || res.stdout || 'Push failed', { kind: 'danger' })
                      } else {
                        pushToast(
                          res.used_credential ? 'Pushed (using saved token)' : 'Pushed',
                          { kind: 'success' },
                        )
                      }
                    } catch (e) {
                      pushToast(e instanceof Error ? e.message : 'Push failed', { kind: 'danger' })
                    } finally {
                      setRemoteBusy(false)
                    }
                  })()
                }}
              >
                Push
              </Button>
            </>
          ) : null}
          <Button
            variant="plain"
            size="sm"
            className={`repo-refresh-btn${gitLoading || discovering || branchSwitching ? ' is-spinning' : ''}`}
            icon={<SyncAltIcon />}
            aria-label={
              gitLoading || discovering || branchSwitching
                ? 'Refreshing repository…'
                : 'Refresh repository'
            }
            title="Refresh"
            isDisabled={gitLoading || discovering || branchSwitching}
            onClick={() => {
              void refreshDiscovery()
                .then(() => refreshLinkedWorktrees())
                .then(() => refreshGit())
                .then(() => loadBranchList())
            }}
          />
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
          liveMode && !selectedRepo.hasGit && !viewingWorktree ? (
            <EmptySplash
              title="Not a git repository"
              body={`No .git found for ${selectedRepo.label}. Clone or init a repo under the workspace path, then Refresh.`}
            />
          ) : changes.length === 0 ? (
            <EmptySplash
              title="Clean working tree"
              body={
                viewingWorktree
                  ? 'No working-tree changes in this isolated worktree.'
                  : 'No working-tree changes in this repository.'
              }
            />
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
                <EmptySplash
                  title="No pull requests"
                  body={
                    fromApi
                      ? 'No local PRs yet. Remote GitHub/GitLab pull requests are not synced in this build — create one here to track work in the studio.'
                      : 'No PRs for this repository yet.'
                  }
                />
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
                <EmptySplash
                  title="No issues"
                  body={
                    fromApi
                      ? 'No local issues yet. Remote GitHub/GitLab issues are not synced in this build — create one here for studio tracking.'
                      : 'No issues for this repository.'
                  }
                />
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
