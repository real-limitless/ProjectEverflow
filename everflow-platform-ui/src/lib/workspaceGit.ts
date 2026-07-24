/**
 * Workspace git helpers for the Playground Repository panel.
 * Live data is read via sandbox exec against /workspace; pure parsers are exported for tests.
 */
import type { GitChangeStatus, GitFileChange, ProjectRepo, RepoProvider } from '@/types/project'
import type { GitCommit } from '@/types/studio'

export interface WorkspaceRepo {
  id: string
  label: string
  path: string
  branch?: string
  url?: string
  provider?: RepoProvider
  hasGit: boolean
}

const MAX_STATUS_DIFFS = 24
const MAX_LOG = 50
const MAX_DIFF_CHARS = 48_000
const FIND_MAXDEPTH = 3

/** Reject path traversal; allow ".", relative segments, no leading /. */
export function sanitizeRepoPath(raw: string | undefined | null): string {
  if (raw == null || raw === '' || raw === '.' || raw === './') return '.'
  let p = String(raw).replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/+$/, '')
  if (!p || p === '.') return '.'
  if (p.startsWith('/') || p.includes('\0')) return '.'
  const parts = p.split('/').filter(Boolean)
  if (parts.some((seg) => seg === '..')) return '.'
  return parts.join('/') || '.'
}

/** Basename-like hint from a label or URL (e.g. org/web → web). */
export function pathHintFromLabel(labelOrUrl: string | undefined): string {
  if (!labelOrUrl) return ''
  let s = labelOrUrl.trim()
  if (!s) return ''
  s = s.replace(/\.git$/i, '')
  try {
    if (/^https?:\/\//i.test(s) || s.startsWith('git@')) {
      const cleaned = s.replace(/^git@[^:]+:/, '').replace(/^https?:\/\/[^/]+\//i, '')
      s = cleaned
    }
  } catch {
    /* keep s */
  }
  const parts = s.split(/[/\\]/).filter(Boolean)
  return parts[parts.length - 1] || ''
}

export function catalogReposToWorkspace(
  catalog: ProjectRepo[] | undefined | null,
): WorkspaceRepo[] {
  const repos = catalog?.length ? catalog : []
  if (repos.length === 0) {
    // No attached remotes — do not invent a ghost "workspace" repo (that drove
    // fake branch dropdowns like experiment/charts on empty API projects).
    return []
  }
  return repos.map((r, i) => {
    // Prefer explicit localPath; fall back to URL/label basename.
    // Never map a cloneable remote to workspace root '.' — each repo has a dir.
    let path = sanitizeRepoPath(r.localPath)
    if (!path || path === '.') {
      const hint =
        pathHintFromLabel(r.url) || pathHintFromLabel(r.label) || pathHintFromLabel(r.id)
      path = sanitizeRepoPath(hint || r.id || `repo-${i}`)
      if (!path || path === '.') path = r.id || `repo-${i}`
    }
    return {
      id: r.id || `repo-${i}`,
      label: r.label || r.id || `repo-${i}`,
      path,
      branch: r.branch,
      url: r.url,
      provider: r.provider,
      hasGit: false,
    }
  })
}

export function statusCodeFromPorcelain(xy: string): GitChangeStatus {
  const x = xy[0] || ' '
  const y = xy[1] || ' '
  const code = y !== ' ' && y !== '?' ? y : x
  if (code === 'A' || code === '?') return 'A'
  if (code === 'D') return 'D'
  if (code === 'R' || code === 'C') return 'R'
  if (code === 'M' || code === 'T' || code === 'U' || code === 'E') return 'M'
  if (x === '?' || y === '?') return 'A'
  return 'U'
}

/**
 * Parse `git status --porcelain=v1 -uall` lines into GitFileChange (no diffs yet).
 * Handles rename lines: `R  old -> new`.
 */
export function parseGitStatusPorcelain(stdout: string): GitFileChange[] {
  const out: GitFileChange[] = []
  const lines = stdout.split(/\r?\n/)
  for (const line of lines) {
    if (line.length < 3) continue
    const xy = line.slice(0, 2)
    let rest = line.slice(3)
    if (!rest) continue
    let path = rest
    let label: string | undefined
    if (xy[0] === 'R' || xy[0] === 'C' || rest.includes(' -> ')) {
      const arrow = rest.lastIndexOf(' -> ')
      if (arrow >= 0) {
        const from = rest.slice(0, arrow).trim()
        const to = rest.slice(arrow + 4).trim()
        path = to || from
        label = to ? `${from} → ${to}` : undefined
      }
    }
    // Untracked: "?? path"
    if (xy === '??' || xy === '!!') {
      path = rest
    }
    path = path.replace(/^"/, '').replace(/"$/, '')
    if (!path || path === '.') continue
    out.push({
      path,
      status: statusCodeFromPorcelain(xy),
      additions: 0,
      deletions: 0,
      label,
    })
  }
  return out
}

export function parseDiffStats(diff: string): { additions: number; deletions: number } {
  let additions = 0
  let deletions = 0
  for (const line of diff.split(/\r?\n/)) {
    if (line.startsWith('+') && !line.startsWith('+++')) additions += 1
    else if (line.startsWith('-') && !line.startsWith('---')) deletions += 1
  }
  return { additions, deletions }
}

export function truncateDiff(diff: string, max = MAX_DIFF_CHARS): string {
  if (diff.length <= max) return diff
  return `${diff.slice(0, max)}\n… (diff truncated)`
}

/**
 * Parse custom log format:
 * %H %x1f %h %x1f %s %x1f %an %x1f %ar %x1f %P %x1f %D
 * Records separated by \x1e (RS).
 */
export function parseGitLog(stdout: string): GitCommit[] {
  const records = stdout.split('\x1e').map((r) => r.trim()).filter(Boolean)
  const commits: GitCommit[] = []
  for (const rec of records) {
    const parts = rec.split('\x1f')
    if (parts.length < 5) continue
    const [hash, shortHash, message, author, when, parentsRaw = '', decor = ''] = parts
    if (!hash) continue
    const parents = parentsRaw
      .trim()
      .split(/\s+/)
      .filter(Boolean)
    const branchLabels = decor
      .split(',')
      .map((s) =>
        s
          .trim()
          .replace(/^HEAD\s*->\s*/i, 'HEAD')
          .replace(/^tag:\s*/i, '')
          .replace(/^origin\//, 'origin/'),
      )
      .filter(Boolean)
    const isHead = branchLabels.some((b) => b === 'HEAD' || b.startsWith('HEAD'))
    commits.push({
      id: hash,
      hash,
      shortHash: shortHash || hash.slice(0, 7),
      message: message || '(no message)',
      author: author || 'unknown',
      when: when || '',
      parents,
      branchLabels: branchLabels.length ? branchLabels : [],
      files: [],
      isHead,
    })
  }
  return commits
}

/** Prefix file paths with repo path for workspace-relative catalogs (Code gutters). */
export function workspaceRelativePath(repoPath: string, filePath: string): string {
  const root = sanitizeRepoPath(repoPath)
  const rel = filePath.replace(/^\.\//, '').replace(/^\/+/, '')
  if (!root || root === '.') return rel
  if (rel.startsWith(`${root}/`)) return rel
  return `${root}/${rel}`
}

export function prefixChanges(
  changes: GitFileChange[],
  repoPath: string,
): GitFileChange[] {
  const root = sanitizeRepoPath(repoPath)
  if (!root || root === '.') return changes
  return changes.map((c) => ({
    ...c,
    path: workspaceRelativePath(root, c.path),
  }))
}

async function gitExec(
  projectId: string,
  repoPath: string,
  args: string[],
  timeoutSeconds = 45,
): Promise<{ exit_code: number; stdout: string; stderr: string }> {
  const { execInSandbox } = await import('@/lib/api')
  const root = sanitizeRepoPath(repoPath)
  const gitArgs = root === '.' ? args : ['-C', root, ...args]
  return execInSandbox(projectId, {
    cmd: 'git',
    args: gitArgs,
    cwd: '/workspace',
    timeout_seconds: timeoutSeconds,
  })
}

/** find(1) exclusions for dependency / build trees (not intentional multi-repo roots). */
const FIND_EXCLUDES = [
  '*/node_modules/*',
  '*/.venv/*',
  '*/venv/*',
  '*/vendor/*',
  '*/.everflow/*',
  '*/dist/*',
  '*/build/*',
  '*/.git/*',
]
  .map((p) => `! -path '${p}'`)
  .join(' ')

async function shellFindGitRoots(projectId: string): Promise<string[]> {
  const { execInSandbox } = await import('@/lib/api')
  // find relative roots ending in /.git → strip suffix; skip dependency / build trees
  const res = await execInSandbox(projectId, {
    cmd: 'sh',
    args: [
      '-c',
      `find . -maxdepth ${FIND_MAXDEPTH} -type d -name .git ${FIND_EXCLUDES} 2>/dev/null | head -40`,
    ],
    cwd: '/workspace',
    timeout_seconds: 20,
  })
  if (res.exit_code !== 0 && !res.stdout.trim()) return []
  const roots: string[] = []
  for (const line of res.stdout.split(/\r?\n/)) {
    const t = line.trim()
    if (!t || !t.includes('.git')) continue
    let root = t.replace(/^\.\//, '').replace(/\/\.git\/?$/, '').replace(/\/\.git$/, '')
    if (!root || root === '.git') root = '.'
    root = sanitizeRepoPath(root)
    if (!roots.includes(root)) roots.push(root)
  }
  return roots
}

/**
 * True only when repoPath is the git work-tree root (not merely inside a parent repo).
 * `git rev-parse --is-inside-work-tree` is too loose: any subfolder of a monorepo returns true.
 * `--show-prefix` is empty exactly at the work-tree root (works for guest /workspace and host paths).
 */
async function probeIsGitRoot(projectId: string, repoPath: string): Promise<boolean> {
  try {
    const root = sanitizeRepoPath(repoPath)
    const inside = await gitExec(projectId, root, ['rev-parse', '--is-inside-work-tree'], 15)
    if (inside.exit_code !== 0 || inside.stdout.trim() !== 'true') return false
    const prefix = await gitExec(projectId, root, ['rev-parse', '--show-prefix'], 15)
    if (prefix.exit_code !== 0) return false
    // Empty prefix ⇒ cwd/root is the work-tree toplevel
    return prefix.stdout.trim() === ''
  } catch {
    return false
  }
}

async function readBranch(projectId: string, repoPath: string): Promise<string | undefined> {
  try {
    const res = await gitExec(projectId, repoPath, ['rev-parse', '--abbrev-ref', 'HEAD'], 15)
    if (res.exit_code === 0) {
      const b = res.stdout.trim()
      if (b && b !== 'HEAD') return b
    }
  } catch {
    /* ignore */
  }
  return undefined
}

function catalogPathCandidates(r: WorkspaceRepo, singleCatalog: boolean): string[] {
  const candidates: string[] = []
  const add = (p: string) => {
    const s = sanitizeRepoPath(p)
    if (!candidates.includes(s)) candidates.push(s)
  }
  add(r.path)
  const hint = pathHintFromLabel(r.label)
  if (hint) add(hint)
  if (r.url) {
    const uh = pathHintFromLabel(r.url)
    if (uh) add(uh)
  }
  // Legacy: only probe workspace root when there is no remote URL (blank scaffold).
  // Remotes always live under /workspace/<name>/ — never bind them to '.'.
  if (singleCatalog && !r.url) add('.')
  return candidates
}

/**
 * Merge catalog repos with live discovery of .git roots under /workspace.
 * Live results only include real git work-tree roots — catalog ghosts without
 * git are dropped so the Repository dropdown never lists "foo (no git)".
 */
export async function discoverWorkspaceRepos(
  projectId: string,
  catalog: ProjectRepo[] | undefined | null,
): Promise<WorkspaceRepo[]> {
  const base = catalogReposToWorkspace(catalog)
  const singleCatalog = (catalog?.length ?? 0) <= 1
  let found: string[] = []
  try {
    found = await shellFindGitRoots(projectId)
  } catch {
    found = []
  }

  // Verify find results are real work-tree roots (ignore empty / broken .git dirs)
  // and never promote Everflow conversation worktrees into the repo catalog.
  const verifiedFound: string[] = []
  for (const root of found) {
    if (isEverflowWorktreePath(root)) continue
    if (await probeIsGitRoot(projectId, root)) verifiedFound.push(root)
  }
  found = verifiedFound

  // Probe catalog paths against true git roots only
  const probed: WorkspaceRepo[] = []
  for (const r of base) {
    const candidates = catalogPathCandidates(r, singleCatalog)
    let resolved: WorkspaceRepo = { ...r, hasGit: false }
    for (const c of candidates) {
      const ok = await probeIsGitRoot(projectId, c)
      if (ok) {
        const branch = (await readBranch(projectId, c)) || r.branch
        resolved = { ...r, path: c, hasGit: true, branch }
        break
      }
    }
    probed.push(resolved)
  }

  // Attach discovered roots not already in list (skip Everflow conversation worktrees)
  const paths = new Set(probed.filter((p) => p.hasGit).map((p) => p.path))
  for (const root of found) {
    if (paths.has(root)) continue
    if (isEverflowWorktreePath(root)) continue
    // Prefer matching catalog by path hint / id / label basename
    const match = probed.find(
      (p) =>
        !p.hasGit &&
        (p.path === root ||
          pathHintFromLabel(p.label) === root ||
          p.id === root ||
          sanitizeRepoPath(p.id) === root),
    )
    if (match) {
      match.path = root
      match.hasGit = true
      match.branch = (await readBranch(projectId, root)) || match.branch
      paths.add(root)
      continue
    }
    const branch = await readBranch(projectId, root)
    const label = root === '.' ? 'workspace' : root
    probed.push({
      id: `ws-${root === '.' ? 'root' : root.replace(/[/\\]/g, '-')}`,
      label,
      path: root,
      branch,
      hasGit: true,
      provider: 'none',
    })
    paths.add(root)
  }

  // Legacy blank projects only: if there is no remote URL and root is a git
  // work tree, bind the catalog entry to '.'. Remotes always use named dirs.
  if (
    singleCatalog &&
    probed.length >= 1 &&
    found.includes('.') &&
    !probed[0].url
  ) {
    probed[0].path = '.'
    probed[0].hasGit = true
    probed[0].branch = (await readBranch(projectId, '.')) || probed[0].branch
  }

  // Prefer real git roots only — drop catalog placeholders like "test (no git)"
  const withGit = probed.filter((p) => p.hasGit)
  if (withGit.length > 0) {
    // Dedupe by path (multiple catalog rows must not collapse to the same root twice)
    const byPath = new Map<string, WorkspaceRepo>()
    for (const r of withGit) {
      if (!byPath.has(r.path)) byPath.set(r.path, r)
    }
    return Array.from(byPath.values())
  }

  // No git in workspace: single entry so the dropdown does not list multiple "(no git)" ghosts
  const fallback = base[0] || {
    id: 'main',
    label: 'workspace',
    path: '.',
    hasGit: false,
  }
  return [{ ...fallback, hasGit: false }]
}

export async function loadGitChanges(
  projectId: string,
  repoPath: string,
  opts?: { withDiffs?: boolean },
): Promise<GitFileChange[]> {
  const withDiffs = opts?.withDiffs !== false
  const status = await gitExec(projectId, repoPath, ['status', '--porcelain=v1', '-uall'], 30)
  if (status.exit_code !== 0) {
    throw new Error(status.stderr.trim() || 'git status failed')
  }
  let changes = parseGitStatusPorcelain(status.stdout)
  if (!withDiffs || changes.length === 0) {
    return prefixChanges(changes, repoPath)
  }

  const limited = changes.slice(0, MAX_STATUS_DIFFS)
  const enriched: GitFileChange[] = []
  for (const c of limited) {
    // For renames, diff the new path
    let diffArgs: string[]
    if (c.status === 'A' || c.status === 'U') {
      // untracked: no HEAD base — try diff /dev/null via status only, or empty
      const untracked = await gitExec(
        projectId,
        repoPath,
        ['diff', '--no-index', '--', '/dev/null', c.path],
        20,
      ).catch(() => null)
      // git diff --no-index exits 1 when different
      const raw =
        untracked && (untracked.stdout || untracked.exit_code === 1)
          ? untracked.stdout
          : ''
      const stats = parseDiffStats(raw)
      enriched.push({
        ...c,
        additions: stats.additions,
        deletions: stats.deletions,
        diffPreview: raw ? truncateDiff(raw) : undefined,
      })
      continue
    }
    if (c.status === 'D') {
      diffArgs = ['diff', 'HEAD', '--', c.path]
    } else {
      // staged + unstaged combined vs HEAD when possible
      diffArgs = ['diff', 'HEAD', '--', c.path]
    }
    const diffRes = await gitExec(projectId, repoPath, diffArgs, 25).catch(() => null)
    let raw = diffRes?.stdout || ''
    if (!raw) {
      const unstaged = await gitExec(projectId, repoPath, ['diff', '--', c.path], 20).catch(
        () => null,
      )
      raw = unstaged?.stdout || ''
    }
    if (!raw) {
      const staged = await gitExec(
        projectId,
        repoPath,
        ['diff', '--cached', '--', c.path],
        20,
      ).catch(() => null)
      raw = staged?.stdout || ''
    }
    const stats = parseDiffStats(raw)
    enriched.push({
      ...c,
      additions: stats.additions,
      deletions: stats.deletions,
      diffPreview: raw ? truncateDiff(raw) : undefined,
    })
  }
  // Append remainder without diffs
  for (const c of changes.slice(MAX_STATUS_DIFFS)) {
    enriched.push(c)
  }
  return prefixChanges(enriched, repoPath)
}

export async function loadGitHistory(
  projectId: string,
  repoPath: string,
  limit = MAX_LOG,
): Promise<GitCommit[]> {
  const fmt = '%H%x1f%h%x1f%s%x1f%an%x1f%ar%x1f%P%x1f%D'
  const res = await gitExec(
    projectId,
    repoPath,
    ['log', `-n`, String(limit), `--pretty=format:%x1e${fmt}`, '--decorate=short'],
    40,
  )
  if (res.exit_code !== 0) {
    throw new Error(res.stderr.trim() || 'git log failed')
  }
  return parseGitLog(res.stdout)
}

export async function loadCommitFiles(
  projectId: string,
  repoPath: string,
  hash: string,
): Promise<string[]> {
  const safeHash = hash.replace(/[^a-fA-F0-9]/g, '')
  if (!safeHash) return []
  const res = await gitExec(
    projectId,
    repoPath,
    ['show', '--name-only', '--pretty=format:', safeHash],
    25,
  )
  if (res.exit_code !== 0) return []
  return res.stdout
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
}

export async function getCurrentBranch(
  projectId: string,
  repoPath: string,
): Promise<string | null> {
  const b = await readBranch(projectId, repoPath)
  return b ?? null
}

/** Allow typical git ref characters; reject traversal / shell metacharacters. */
export function sanitizeBranchName(raw: string | undefined | null): string | null {
  if (raw == null) return null
  const name = String(raw).trim()
  if (!name || name.length > 255) return null
  if (name === 'HEAD' || name === '@') return null
  if (name.includes('..') || name.includes('\\') || name.includes('\0')) return null
  if (name.startsWith('-') || name.startsWith('/') || name.endsWith('/')) return null
  if (!/^[A-Za-z0-9._/\-]+$/.test(name)) return null
  return name
}

export interface BranchListItem {
  name: string
  /** true for origin/* etc. */
  remote?: boolean
}

/**
 * List local branches (and optionally remotes). Current branch is not marked here —
 * callers compare against getCurrentBranch / liveBranch.
 */
export async function listBranches(
  projectId: string,
  repoPath: string,
  opts?: { remotes?: boolean },
): Promise<BranchListItem[]> {
  const local = await gitExec(projectId, repoPath, ['branch', '--format=%(refname:short)'], 20)
  const out: BranchListItem[] = []
  const seen = new Set<string>()
  if (local.exit_code === 0) {
    for (const line of local.stdout.split(/\r?\n/)) {
      const name = sanitizeBranchName(line.trim())
      if (!name || seen.has(name)) continue
      seen.add(name)
      out.push({ name })
    }
  }
  if (opts?.remotes !== false) {
    const remote = await gitExec(
      projectId,
      repoPath,
      ['branch', '-r', '--format=%(refname:short)'],
      20,
    ).catch(() => null)
    if (remote && remote.exit_code === 0) {
      for (const line of remote.stdout.split(/\r?\n/)) {
        let raw = line.trim()
        // skip "origin/HEAD -> origin/main"
        if (raw.includes('->')) continue
        const name = sanitizeBranchName(raw)
        if (!name || seen.has(name)) continue
        seen.add(name)
        out.push({ name, remote: true })
      }
    }
  }
  return out
}

/**
 * Checkout a branch in the workspace repo. Returns the new branch name on success.
 */
export async function checkoutBranch(
  projectId: string,
  repoPath: string,
  branch: string,
): Promise<{ ok: true; branch: string } | { ok: false; error: string }> {
  const name = sanitizeBranchName(branch)
  if (!name) return { ok: false, error: 'Invalid branch name' }

  // Prefer local branch; for remote-only names try checkout -B track
  const isRemote = name.includes('/')
  let res
  if (isRemote && name.startsWith('origin/')) {
    const localName = sanitizeBranchName(name.replace(/^origin\//, ''))
    if (localName) {
      res = await gitExec(
        projectId,
        repoPath,
        ['checkout', '-B', localName, '--track', name],
        60,
      ).catch((e) => ({
        exit_code: 1,
        stdout: '',
        stderr: e instanceof Error ? e.message : String(e),
      }))
      if (res.exit_code === 0) {
        const b = (await readBranch(projectId, repoPath)) || localName
        return { ok: true, branch: b }
      }
    }
  }

  res = await gitExec(projectId, repoPath, ['checkout', name], 60).catch((e) => ({
    exit_code: 1,
    stdout: '',
    stderr: e instanceof Error ? e.message : String(e),
  }))
  if (res.exit_code !== 0) {
    const msg = (res.stderr || res.stdout || 'git checkout failed').trim()
    return { ok: false, error: msg.slice(0, 400) }
  }
  const b = (await readBranch(projectId, repoPath)) || name
  return { ok: true, branch: b }
}

// ── Conversation worktrees (opt-in isolated checkouts) ──────────────────────

export const EVERFLOW_WORKTREE_PREFIX = '.everflow/worktrees'
export const WORKTREE_INDEX_PATH = '.everflow/worktrees/index.json'

/** True when path is under Everflow-managed conversation worktrees. */
export function isEverflowWorktreePath(path: string | undefined | null): boolean {
  const p = sanitizeRepoPath(path)
  if (!p || p === '.') return false
  return p === EVERFLOW_WORKTREE_PREFIX || p.startsWith(`${EVERFLOW_WORKTREE_PREFIX}/`)
}

/** Allow session ids like `ses_…` / `n123` for path segments. */
export function sanitizeWorktreeSessionId(raw: string | undefined | null): string | null {
  if (raw == null) return null
  const s = String(raw).trim()
  if (!s || s.length > 128) return null
  if (!/^[A-Za-z0-9._-]+$/.test(s)) return null
  return s
}

/** Sanitize repo id for a single path segment under .everflow/worktrees/. */
export function sanitizeWorktreeRepoId(raw: string | undefined | null): string | null {
  if (raw == null) return null
  let s = String(raw).trim().replace(/\\/g, '/')
  if (!s) return null
  s = s.replace(/^\.\//, '').replace(/\/+$/, '')
  if (!s || s === '.' || s.includes('..') || s.includes('\0')) return null
  s = s.replace(/[/\\]+/g, '-')
  if (!/^[A-Za-z0-9._-]+$/.test(s) || s.length > 80) return null
  return s
}

export function worktreeBranchForSession(sessionId: string): string | null {
  const id = sanitizeWorktreeSessionId(sessionId)
  if (!id) return null
  const short = id.replace(/^ses_/, '').slice(0, 16) || id.slice(0, 16)
  return sanitizeBranchName(`ef/${short}`)
}

export function worktreePathForSession(repoId: string, sessionId: string): string | null {
  const rid = sanitizeWorktreeRepoId(repoId)
  const sid = sanitizeWorktreeSessionId(sessionId)
  if (!rid || !sid) return null
  return `${EVERFLOW_WORKTREE_PREFIX}/${rid}/${sid}`
}

/** Normalize absolute guest paths (`/workspace/foo`) to workspace-relative. */
export function workspaceRelFromAbsPath(absoluteOrRel: string): string {
  let p = String(absoluteOrRel || '')
    .replace(/\\/g, '/')
    .trim()
  if (p.startsWith('/workspace/')) p = p.slice('/workspace/'.length)
  else if (p === '/workspace' || p === '/workspace/') p = '.'
  return sanitizeRepoPath(p)
}

export interface WorktreeListEntry {
  path: string
  head?: string
  branch?: string
  bare?: boolean
  detached?: boolean
  locked?: boolean
  prunable?: boolean
}

/**
 * Parse `git worktree list --porcelain` into workspace-relative entries.
 */
export function parseWorktreePorcelain(stdout: string): WorktreeListEntry[] {
  const entries: WorktreeListEntry[] = []
  let cur: WorktreeListEntry | null = null
  const flush = () => {
    if (cur?.path) entries.push(cur)
    cur = null
  }
  for (const rawLine of stdout.split(/\r?\n/)) {
    const line = rawLine.trimEnd()
    if (!line) {
      flush()
      continue
    }
    if (line.startsWith('worktree ')) {
      flush()
      const abs = line.slice('worktree '.length).trim()
      cur = { path: workspaceRelFromAbsPath(abs) }
      continue
    }
    if (!cur) continue
    if (line.startsWith('HEAD ')) cur.head = line.slice(5).trim()
    else if (line.startsWith('branch ')) {
      const ref = line.slice('branch '.length).trim()
      cur.branch = ref.replace(/^refs\/heads\//, '')
    } else if (line === 'bare') cur.bare = true
    else if (line === 'detached') cur.detached = true
    else if (line.startsWith('locked')) cur.locked = true
    else if (line === 'prunable' || line.startsWith('prunable ')) cur.prunable = true
  }
  flush()
  return entries
}

export type ConversationWorktreeStatus = 'active' | 'applied' | 'discarded' | 'error'

export interface ConversationWorktreeMeta {
  sessionId: string
  repoId: string
  parentPath: string
  path: string
  branch: string
  status: ConversationWorktreeStatus
  error?: string
}

export interface WorktreeIndexFile {
  entries: ConversationWorktreeMeta[]
}

export function parseWorktreeIndexJson(raw: string): WorktreeIndexFile {
  try {
    const data = JSON.parse(raw) as unknown
    if (!data || typeof data !== 'object') return { entries: [] }
    const entries = Array.isArray((data as WorktreeIndexFile).entries)
      ? (data as WorktreeIndexFile).entries
      : []
    return {
      entries: entries.filter(
        (e): e is ConversationWorktreeMeta =>
          Boolean(
            e &&
              typeof e === 'object' &&
              typeof e.sessionId === 'string' &&
              typeof e.path === 'string' &&
              typeof e.branch === 'string' &&
              typeof e.parentPath === 'string' &&
              typeof e.repoId === 'string',
          ),
      ),
    }
  } catch {
    return { entries: [] }
  }
}

/** Pure command plan for discard (from parent repo). */
export function planDiscardWorktreeCommands(
  worktreePath: string,
  branch: string,
): string[][] {
  const wt = sanitizeRepoPath(worktreePath)
  const b = sanitizeBranchName(branch)
  const cmds: string[][] = []
  if (wt && wt !== '.') cmds.push(['worktree', 'remove', '--force', wt])
  if (b) cmds.push(['branch', '-D', b])
  return cmds
}

/** Pure command plan for approve merge (from parent after worktree is committed). */
export function planApproveMergeCommands(branch: string): string[][] {
  const b = sanitizeBranchName(branch)
  if (!b) return []
  return [
    ['merge', '--no-edit', b],
    ['worktree', 'remove', '--force'], // path filled by caller
    ['branch', '-D', b],
  ]
}

async function ensureParentDirs(projectId: string, relPath: string): Promise<void> {
  const { execInSandbox } = await import('@/lib/api')
  const parent = relPath.includes('/') ? relPath.replace(/\/[^/]+$/, '') : ''
  if (!parent) return
  await execInSandbox(projectId, {
    cmd: 'mkdir',
    args: ['-p', parent],
    cwd: '/workspace',
    timeout_seconds: 15,
  })
}

export async function listWorktrees(
  projectId: string,
  repoPath: string,
): Promise<WorktreeListEntry[]> {
  const res = await gitExec(projectId, repoPath, ['worktree', 'list', '--porcelain'], 30)
  if (res.exit_code !== 0) {
    throw new Error(res.stderr.trim() || 'git worktree list failed')
  }
  return parseWorktreePorcelain(res.stdout)
}

/** After a miss, skip re-reads briefly — chat/session refresh used to hammer a missing index. */
const worktreeIndexMissUntil = new Map<string, number>()
const WORKTREE_INDEX_MISS_BACKOFF_MS = 30_000

function shouldBackoffWorktreeIndex(status: number): boolean {
  // 404 = file not created yet; 409 = sandbox not ready / transitional.
  return status === 404 || status === 409 || status === 502 || status === 503
}

export async function readWorktreeIndex(projectId: string): Promise<WorktreeIndexFile> {
  const until = worktreeIndexMissUntil.get(projectId) || 0
  if (Date.now() < until) {
    return { entries: [] }
  }
  try {
    const { readSandboxFs } = await import('@/lib/api')
    const raw = await readSandboxFs(projectId, WORKTREE_INDEX_PATH)
    worktreeIndexMissUntil.delete(projectId)
    return parseWorktreeIndexJson(raw)
  } catch (e) {
    const { ApiError } = await import('@/lib/api')
    if (e instanceof ApiError && shouldBackoffWorktreeIndex(e.status)) {
      worktreeIndexMissUntil.set(projectId, Date.now() + WORKTREE_INDEX_MISS_BACKOFF_MS)
    }
    return { entries: [] }
  }
}

export async function writeWorktreeIndex(
  projectId: string,
  index: WorktreeIndexFile,
): Promise<void> {
  const { writeSandboxFs } = await import('@/lib/api')
  await ensureParentDirs(projectId, WORKTREE_INDEX_PATH)
  await writeSandboxFs(projectId, WORKTREE_INDEX_PATH, JSON.stringify(index, null, 2))
}

export async function upsertWorktreeIndexEntry(
  projectId: string,
  entry: ConversationWorktreeMeta,
): Promise<void> {
  const index = await readWorktreeIndex(projectId)
  const next = index.entries.filter((e) => e.sessionId !== entry.sessionId)
  next.push(entry)
  await writeWorktreeIndex(projectId, { entries: next })
}

export type EnsureWorktreeResult =
  | {
      ok: true
      path: string
      branch: string
      parentPath: string
      repoId: string
      reused: boolean
    }
  | { ok: false; error: string }

/**
 * Create (or reuse) a conversation worktree under `.everflow/worktrees/<repoId>/<sessionId>`.
 */
export async function ensureConversationWorktree(
  projectId: string,
  opts: {
    repoId: string
    parentPath: string
    sessionId: string
    baseBranch?: string | null
  },
): Promise<EnsureWorktreeResult> {
  const parentPath = sanitizeRepoPath(opts.parentPath)
  const path = worktreePathForSession(opts.repoId, opts.sessionId)
  const branch = worktreeBranchForSession(opts.sessionId)
  if (!path || !branch) {
    return { ok: false, error: 'Invalid session or repo id for worktree' }
  }
  if (!(await probeIsGitRoot(projectId, parentPath))) {
    return { ok: false, error: 'Parent path is not a git repository' }
  }

  // Reuse existing worktree at path
  if (await probeIsGitRoot(projectId, path)) {
    const meta: ConversationWorktreeMeta = {
      sessionId: opts.sessionId,
      repoId: opts.repoId,
      parentPath,
      path,
      branch,
      status: 'active',
    }
    await upsertWorktreeIndexEntry(projectId, meta).catch(() => undefined)
    return { ok: true, path, branch, parentPath, repoId: opts.repoId, reused: true }
  }

  await ensureParentDirs(projectId, path)

  const base = sanitizeBranchName(opts.baseBranch) || undefined
  // Prefer create new branch from base (or HEAD); if branch exists, attach path to it.
  let res = await gitExec(
    projectId,
    parentPath,
    base
      ? ['worktree', 'add', '-b', branch, path, base]
      : ['worktree', 'add', '-b', branch, path],
    90,
  ).catch((e) => ({
    exit_code: 1,
    stdout: '',
    stderr: e instanceof Error ? e.message : String(e),
  }))

  if (res.exit_code !== 0) {
    const err = (res.stderr || res.stdout || '').toLowerCase()
    if (err.includes('already exists') || err.includes('already checked out')) {
      res = await gitExec(projectId, parentPath, ['worktree', 'add', path, branch], 90).catch(
        (e) => ({
          exit_code: 1,
          stdout: '',
          stderr: e instanceof Error ? e.message : String(e),
        }),
      )
    }
  }

  if (res.exit_code !== 0) {
    const msg = (res.stderr || res.stdout || 'git worktree add failed').trim().slice(0, 400)
    return { ok: false, error: msg }
  }

  const meta: ConversationWorktreeMeta = {
    sessionId: opts.sessionId,
    repoId: opts.repoId,
    parentPath,
    path,
    branch,
    status: 'active',
  }
  await upsertWorktreeIndexEntry(projectId, meta).catch(() => undefined)
  return { ok: true, path, branch, parentPath, repoId: opts.repoId, reused: false }
}

export async function diffWorktree(
  projectId: string,
  worktreePath: string,
): Promise<{ changes: Awaited<ReturnType<typeof loadGitChanges>>; branch: string | null }> {
  const path = sanitizeRepoPath(worktreePath)
  const [changes, branch] = await Promise.all([
    loadGitChanges(projectId, path, { withDiffs: true }),
    getCurrentBranch(projectId, path),
  ])
  return { changes, branch }
}

async function commitWorktreeIfDirty(
  projectId: string,
  worktreePath: string,
  message: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const status = await gitExec(projectId, worktreePath, ['status', '--porcelain=v1'], 30)
  if (status.exit_code !== 0) {
    return { ok: false, error: status.stderr.trim() || 'git status failed in worktree' }
  }
  if (!status.stdout.trim()) return { ok: true }

  const add = await gitExec(projectId, worktreePath, ['add', '-A'], 60)
  if (add.exit_code !== 0) {
    return { ok: false, error: add.stderr.trim() || 'git add failed in worktree' }
  }
  // Identity for sandbox commits (local only)
  await gitExec(projectId, worktreePath, ['config', 'user.email', 'everflow@local'], 15).catch(
    () => null,
  )
  await gitExec(projectId, worktreePath, ['config', 'user.name', 'Everflow'], 15).catch(() => null)

  const commit = await gitExec(
    projectId,
    worktreePath,
    ['commit', '-m', message, '--allow-empty-message'],
    60,
  )
  if (commit.exit_code !== 0) {
    const msg = (commit.stderr || commit.stdout || 'git commit failed').trim()
    // Nothing to commit race
    if (/nothing to commit/i.test(msg)) return { ok: true }
    return { ok: false, error: msg.slice(0, 400) }
  }
  return { ok: true }
}

export type WorktreeActionResult =
  | { ok: true; parentBranch?: string }
  | { ok: false; error: string }

/**
 * Merge worktree branch into the parent checkout's current branch, then remove the worktree.
 */
export async function approveWorktree(
  projectId: string,
  opts: {
    parentPath: string
    worktreePath: string
    branch: string
    sessionId?: string
  },
): Promise<WorktreeActionResult> {
  const parentPath = sanitizeRepoPath(opts.parentPath)
  const worktreePath = sanitizeRepoPath(opts.worktreePath)
  const branch = sanitizeBranchName(opts.branch)
  if (!branch) return { ok: false, error: 'Invalid worktree branch' }
  if (!isEverflowWorktreePath(worktreePath)) {
    return { ok: false, error: 'Refusing to approve a non-Everflow worktree path' }
  }

  const committed = await commitWorktreeIfDirty(
    projectId,
    worktreePath,
    `ef: chat worktree ${branch}`,
  )
  if (!committed.ok) return committed

  const parentBranch = await readBranch(projectId, parentPath)
  const merge = await gitExec(projectId, parentPath, ['merge', '--no-edit', branch], 120).catch(
    (e) => ({
      exit_code: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }),
  )
  if (merge.exit_code !== 0) {
    // Abort merge if conflict left repo in merging state
    const msg = (merge.stderr || merge.stdout || 'merge failed').trim()
    if (/conflict/i.test(msg)) {
      await gitExec(projectId, parentPath, ['merge', '--abort'], 30).catch(() => null)
    }
    return { ok: false, error: msg.slice(0, 400) }
  }

  const remove = await gitExec(
    projectId,
    parentPath,
    ['worktree', 'remove', '--force', worktreePath],
    60,
  ).catch((e) => ({
    exit_code: 1,
    stdout: '',
    stderr: e instanceof Error ? e.message : String(e),
  }))
  if (remove.exit_code !== 0) {
    return {
      ok: false,
      error: (remove.stderr || remove.stdout || 'worktree remove failed').trim().slice(0, 400),
    }
  }

  await gitExec(projectId, parentPath, ['branch', '-D', branch], 30).catch(() => null)

  if (opts.sessionId) {
    const index = await readWorktreeIndex(projectId)
    const entries = index.entries.map((e) =>
      e.sessionId === opts.sessionId
        ? { ...e, status: 'applied' as const, error: undefined }
        : e,
    )
    await writeWorktreeIndex(projectId, { entries }).catch(() => undefined)
  }

  return { ok: true, parentBranch: parentBranch || undefined }
}

export async function discardWorktree(
  projectId: string,
  opts: {
    parentPath: string
    worktreePath: string
    branch: string
    sessionId?: string
  },
): Promise<WorktreeActionResult> {
  const parentPath = sanitizeRepoPath(opts.parentPath)
  const worktreePath = sanitizeRepoPath(opts.worktreePath)
  const branch = sanitizeBranchName(opts.branch)
  if (!branch) return { ok: false, error: 'Invalid worktree branch' }
  if (!isEverflowWorktreePath(worktreePath)) {
    return { ok: false, error: 'Refusing to discard a non-Everflow worktree path' }
  }

  for (const args of planDiscardWorktreeCommands(worktreePath, branch)) {
    const res = await gitExec(projectId, parentPath, args, 60).catch((e) => ({
      exit_code: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }))
    // Ignore "not a working tree" / missing branch on cleanup
    if (res.exit_code !== 0) {
      const msg = (res.stderr || res.stdout || '').toLowerCase()
      if (
        msg.includes('not a working tree') ||
        msg.includes('does not exist') ||
        msg.includes('not found') ||
        msg.includes('no such')
      ) {
        continue
      }
      if (args[0] === 'worktree') {
        return { ok: false, error: (res.stderr || res.stdout || 'discard failed').trim().slice(0, 400) }
      }
    }
  }

  if (opts.sessionId) {
    const index = await readWorktreeIndex(projectId)
    const entries = index.entries.map((e) =>
      e.sessionId === opts.sessionId
        ? { ...e, status: 'discarded' as const, error: undefined }
        : e,
    )
    await writeWorktreeIndex(projectId, { entries }).catch(() => undefined)
  }

  return { ok: true }
}

/** System prompt fragment so OpenCode edits stay inside the worktree. */
export function worktreeSystemPrompt(worktreePath: string, parentPath: string): string {
  const wt = sanitizeRepoPath(worktreePath)
  const parent = sanitizeRepoPath(parentPath)
  const wtAbs = wt === '.' ? '/workspace' : `/workspace/${wt}`
  const parentAbs = parent === '.' ? '/workspace' : `/workspace/${parent}`
  return [
    `You are working in an isolated git worktree.`,
    `Working directory (edit only here): ${wtAbs}`,
    `Do not modify files under the parent checkout: ${parentAbs}`,
    `Prefer paths relative to ${wtAbs}. Leave the parent tree unchanged until the user approves.`,
  ].join(' ')
}
