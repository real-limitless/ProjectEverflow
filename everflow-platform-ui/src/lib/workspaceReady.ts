/**
 * Wait until the sandbox workspace has been seeded/cloned after provision.
 * Platform marks sandbox_status=running before background clone/toolkit seed finishes.
 */
import { getProject as apiGetProject, listSandboxFs } from '@/lib/api'
import { isCloneableUrl, mergeApiProjectRepos } from '@/lib/workspaceRepos'
import type { ProjectRepo } from '@/types/project'

const DEFAULT_INTERVAL_MS = 1500
const DEFAULT_TIMEOUT_MS = 90_000

export type WorkspaceReadyReason =
  | 'repos_ready'
  | 'fs_populated'
  | 'blank_ok'
  | 'timeout'
  | 'cancelled'

export type WorkspaceReadyResult = {
  ready: boolean
  repos: ProjectRepo[]
  entryCount: number
  reason: WorkspaceReadyReason
}

function meaningfulFsCount(
  entries: Array<{ name?: string; is_dir?: boolean }>,
): number {
  return entries.filter((e) => {
    const n = (e.name || '').trim()
    return n && n !== '.' && n !== '..'
  }).length
}

function cloneablePending(repos: ProjectRepo[]): boolean {
  return repos.some(
    (r) =>
      isCloneableUrl(r.url) &&
      r.cloneStatus !== 'ready' &&
      r.cloneStatus !== 'skipped' &&
      r.cloneStatus !== 'error',
  )
}

function anyCloneReady(repos: ProjectRepo[]): boolean {
  return repos.some((r) => isCloneableUrl(r.url) && r.cloneStatus === 'ready')
}

function seededLocalReady(repos: ProjectRepo[]): boolean {
  return repos.some(
    (r) =>
      r.cloneStatus === 'ready' &&
      Boolean(r.localPath && r.localPath !== '.'),
  )
}

export type WaitForWorkspaceOpts = {
  /** True when the project should receive toolkit files or git remotes. */
  expectContent: boolean
  localRepos?: ProjectRepo[] | null
  onUpdate?: (message: string) => void
  isCancelled?: () => boolean
  intervalMs?: number
  timeoutMs?: number
}

/**
 * Poll project + sandbox FS until workspace content appears (or blank settles).
 */
export async function waitForWorkspaceReady(
  projectId: string,
  opts: WaitForWorkspaceOpts,
): Promise<WorkspaceReadyResult> {
  const intervalMs = opts.intervalMs ?? DEFAULT_INTERVAL_MS
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const started = Date.now()
  let repos = opts.localRepos ? [...opts.localRepos] : []
  let entryCount = 0
  let sawSuccessfulFs = false

  while (Date.now() - started < timeoutMs) {
    if (opts.isCancelled?.()) {
      return { ready: false, repos, entryCount, reason: 'cancelled' }
    }

    try {
      const fresh = await apiGetProject(projectId)
      repos = mergeApiProjectRepos(fresh, repos)
    } catch {
      /* keep last repos */
    }

    try {
      const entries = await listSandboxFs(projectId, '.')
      entryCount = meaningfulFsCount(entries)
      sawSuccessfulFs = true
    } catch {
      opts.onUpdate?.('Waiting for workspace filesystem…')
      await sleep(intervalMs)
      continue
    }

    const hasCloneable = repos.some((r) => isCloneableUrl(r.url))

    if (hasCloneable) {
      if (cloneablePending(repos)) {
        opts.onUpdate?.('Cloning repositories into workspace…')
        await sleep(intervalMs)
        continue
      }
      if (anyCloneReady(repos) || entryCount > 0) {
        return { ready: true, repos, entryCount, reason: 'repos_ready' }
      }
      // All remotes failed/skipped and FS still empty — stop waiting
      return { ready: true, repos, entryCount, reason: 'repos_ready' }
    }

    if (opts.expectContent) {
      if (seededLocalReady(repos) || entryCount > 0) {
        return {
          ready: true,
          repos,
          entryCount,
          reason: seededLocalReady(repos) ? 'repos_ready' : 'fs_populated',
        }
      }
      opts.onUpdate?.('Seeding project files into workspace…')
      await sleep(intervalMs)
      continue
    }

    // Blank / no expected content: one successful FS list is enough
    if (sawSuccessfulFs) {
      return { ready: true, repos, entryCount, reason: 'blank_ok' }
    }

    await sleep(intervalMs)
  }

  return { ready: entryCount > 0 || !opts.expectContent, repos, entryCount, reason: 'timeout' }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}
