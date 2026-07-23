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
    return [{ id: 'main', label: 'workspace', path: '.', hasGit: false }]
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
  const verifiedFound: string[] = []
  for (const root of found) {
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

  // Attach discovered roots not already in list
  const paths = new Set(probed.filter((p) => p.hasGit).map((p) => p.path))
  for (const root of found) {
    if (paths.has(root)) continue
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
