/**
 * Ensure catalog remotes are cloned into the sandbox workspace.
 * Complements server-side clone after provision; used for recovery, retry, and demo-less paths.
 */
import type { ApiProject, ApiProjectRepo } from './api'
import { pathHintFromLabel, sanitizeRepoPath } from './workspaceGit'
import type { ProjectRepo, RepoProvider } from '@/types/project'

const CLONE_TIMEOUT = 300

export function isCloneableUrl(url: string | undefined | null): boolean {
  if (!url) return false
  const s = url.trim()
  if (!s) return false
  return (
    s.startsWith('https://') ||
    s.startsWith('http://') ||
    s.startsWith('git@') ||
    s.startsWith('ssh://')
  )
}

export function apiReposToProjectRepos(apiRepos: ApiProjectRepo[] | null | undefined): ProjectRepo[] {
  if (!apiRepos?.length) return []
  return apiRepos.map((r, i) => ({
    id: r.id || `repo-${i}`,
    label: r.label || r.id || `repo-${i}`,
    active: Boolean(r.active),
    url: r.url || undefined,
    branch: r.branch || 'main',
    provider: (r.provider as RepoProvider) || 'github',
    localPath: r.local_path || undefined,
    cloneStatus: r.clone_status || undefined,
    cloneError: r.clone_error || undefined,
  }))
}

/** Map UI ProjectRepo → API create payload shape. */
export function projectReposToApiPayload(repos: ProjectRepo[]): Array<{
  id: string
  label: string
  url?: string
  branch?: string
  provider?: string
  local_path?: string
  active?: boolean
}> {
  return repos
    .filter((r) => r.label || r.url)
    .map((r, i) => ({
      id: r.id || `repo-${i}`,
      label: r.label || pathHintFromLabel(r.url) || `repo-${i}`,
      url: r.url?.trim() || undefined,
      branch: r.branch || 'main',
      provider: r.provider || (r.url ? 'github' : 'none'),
      local_path: r.localPath,
      active: Boolean(r.active),
    }))
}

/** Named directory under /workspace for a remote (never '.'). */
export function namedRepoDir(r: {
  url?: string
  label?: string
  id?: string
  localPath?: string
}): string {
  const preferred = sanitizeRepoPath(r.localPath || '')
  if (preferred && preferred !== '.' && !preferred.includes('/')) {
    return preferred
  }
  return (
    pathHintFromLabel(r.url) ||
    pathHintFromLabel(r.label) ||
    pathHintFromLabel(r.id) ||
    'repo'
  )
}

/** Normalize draft repos with localPath hints before create. */
export function normalizeReposForCreate(repos: ProjectRepo[]): ProjectRepo[] {
  const used = new Set<string>()
  let sawActive = false
  return repos
    .map((r, i) => {
      const url = r.url?.trim()
      let localPath = r.localPath
      if (isCloneableUrl(url)) {
        // Every remote gets its own directory under /workspace
        let dest = namedRepoDir({ ...r, url })
        let base = dest
        let n = 2
        while (used.has(dest)) {
          dest = `${base}-${n}`
          n++
        }
        used.add(dest)
        localPath = dest
      }
      let active = Boolean(r.active)
      if (active && !sawActive) sawActive = true
      else if (active && sawActive) active = false
      return {
        ...r,
        id: r.id || `repo-${i}`,
        url: url || undefined,
        branch: r.branch || 'main',
        provider: r.provider || (url ? 'github' : 'none'),
        localPath,
        active,
        cloneStatus: isCloneableUrl(url) ? r.cloneStatus || 'pending' : 'skipped',
      }
    })
    .map((r, _i, arr) => {
      if (!sawActive && arr[0] && r.id === arr[0].id) return { ...r, active: true }
      return r
    })
}

async function probeGitRoot(projectId: string, repoPath: string): Promise<boolean> {
  const { execInSandbox } = await import('@/lib/api')
  const root = sanitizeRepoPath(repoPath)
  const args =
    root === '.'
      ? ['rev-parse', '--is-inside-work-tree']
      : ['-C', root, 'rev-parse', '--is-inside-work-tree']
  try {
    const inside = await execInSandbox(projectId, {
      cmd: 'git',
      args,
      cwd: '/workspace',
      timeout_seconds: 15,
    })
    if (inside.exit_code !== 0 || inside.stdout.trim() !== 'true') return false
    const prefixArgs =
      root === '.'
        ? ['rev-parse', '--show-prefix']
        : ['-C', root, 'rev-parse', '--show-prefix']
    const prefix = await execInSandbox(projectId, {
      cmd: 'git',
      args: prefixArgs,
      cwd: '/workspace',
      timeout_seconds: 15,
    })
    return prefix.exit_code === 0 && prefix.stdout.trim() === ''
  } catch {
    return false
  }
}

async function readBranch(projectId: string, repoPath: string): Promise<string | undefined> {
  const { execInSandbox } = await import('@/lib/api')
  const root = sanitizeRepoPath(repoPath)
  const args =
    root === '.'
      ? ['rev-parse', '--abbrev-ref', 'HEAD']
      : ['-C', root, 'rev-parse', '--abbrev-ref', 'HEAD']
  try {
    const res = await execInSandbox(projectId, {
      cmd: 'git',
      args,
      cwd: '/workspace',
      timeout_seconds: 15,
    })
    if (res.exit_code === 0) {
      const b = res.stdout.trim()
      if (b && b !== 'HEAD') return b
    }
  } catch {
    /* ignore */
  }
  return undefined
}

export type EnsureReposResult = {
  repos: ProjectRepo[]
  cloned: number
  failed: number
  skipped: number
}

/**
 * For each catalog remote with a URL, ensure a git work tree exists under /workspace.
 * Idempotent: skips when already a git root.
 */
export async function ensureReposCloned(
  projectId: string,
  repos: ProjectRepo[],
): Promise<EnsureReposResult> {
  const { execInSandbox } = await import('@/lib/api')

  let cloned = 0
  let failed = 0
  let skipped = 0
  const out: ProjectRepo[] = []
  const used = new Set<string>()

  for (const r of repos) {
    if (!isCloneableUrl(r.url)) {
      out.push({ ...r, cloneStatus: r.cloneStatus || 'skipped' })
      skipped++
      continue
    }

    // Every remote → /workspace/<name>/ (never workspace root)
    let dest = namedRepoDir(r)
    let base = dest
    let n = 2
    while (used.has(dest)) {
      dest = `${base}-${n}`
      n++
    }
    used.add(dest)

    if (await probeGitRoot(projectId, dest)) {
      const branch = (await readBranch(projectId, dest)) || r.branch
      out.push({
        ...r,
        localPath: dest,
        branch,
        cloneStatus: 'ready',
        cloneError: undefined,
      })
      skipped++
      continue
    }

    const url = r.url!.trim()
    const branch = (r.branch || 'main').trim() || 'main'
    const branchArg = branch.replace(/[^A-Za-z0-9._/\-]/g, '')

    const script = [
      'set -e',
      'cd /workspace',
      `(git clone --depth 1 -b ${JSON.stringify(branchArg)} -- ${JSON.stringify(url)} ${JSON.stringify(dest)} || git clone --depth 1 -- ${JSON.stringify(url)} ${JSON.stringify(dest)})`,
      `test -d ${JSON.stringify(`${dest}/.git`)}`,
    ].join('; ')

    try {
      const res = await execInSandbox(projectId, {
        cmd: 'sh',
        args: ['-c', script],
        cwd: '/workspace',
        timeout_seconds: CLONE_TIMEOUT,
      })
      if (res.exit_code !== 0) {
        let err = (res.stderr || res.stdout || 'git clone failed').trim().slice(-1500)
        const low = err.toLowerCase()
        if (
          low.includes('authentication') ||
          low.includes('403') ||
          low.includes('could not read username')
        ) {
          err +=
            '\n\nPrivate repositories need a GitHub token (not configured yet). Use a public HTTPS URL for now.'
        }
        out.push({
          ...r,
          localPath: dest,
          cloneStatus: 'error',
          cloneError: err,
        })
        failed++
        continue
      }
      const liveBranch = (await readBranch(projectId, dest)) || branch
      out.push({
        ...r,
        localPath: dest,
        branch: liveBranch,
        cloneStatus: 'ready',
        cloneError: undefined,
      })
      cloned++
    } catch (e) {
      out.push({
        ...r,
        localPath: dest,
        cloneStatus: 'error',
        cloneError: e instanceof Error ? e.message : 'Clone failed',
      })
      failed++
    }
  }

  return { repos: out, cloned, failed, skipped }
}

/** Merge API project repos into catalog-shaped ProjectRepo[], preferring API clone status. */
export function mergeApiProjectRepos(
  apiProject: ApiProject,
  existing?: ProjectRepo[],
): ProjectRepo[] {
  const fromApi = apiReposToProjectRepos(apiProject.repos)
  if (fromApi.length) {
    // Ensure one active
    if (!fromApi.some((r) => r.active) && fromApi[0]) fromApi[0].active = true
    return fromApi
  }
  return existing || []
}
