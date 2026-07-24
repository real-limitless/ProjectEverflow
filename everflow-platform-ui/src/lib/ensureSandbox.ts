import {
  getSandboxStatus,
  recreateSandbox,
  startSandbox,
  type SandboxStatus,
} from '@/lib/api'
import {
  SANDBOX_POLL_INTERVAL_MS,
  SANDBOX_POLL_TIMEOUT_MS,
  waitForSandbox,
} from '@/lib/sandboxPoll'
import {
  shouldRecreateSandbox,
  withEffectiveSandboxStatus,
} from '@/lib/sandboxReady'

export type EnsureSandboxResult = {
  status: SandboxStatus
  action: 'none' | 'poll' | 'start' | 'recreate'
  ok: boolean
}

type EnsureOpts = {
  onUpdate?: (status: SandboxStatus) => void
  /** Force recreate even if status is pending/creating (Retry). */
  forceRecreate?: boolean
  intervalMs?: number
  timeoutMs?: number
}

const inflight = new Map<string, Promise<EnsureSandboxResult>>()
/** Consecutive dead observations before auto-recreate (avoids single blip storms). */
const deadObservations = new Map<string, number>()
const recreateCooldownUntil = new Map<string, number>()
const DEAD_OBSERVATIONS_NEEDED = 2
const RECREATE_COOLDOWN_MS = 20_000

function applyUpdate(
  st: SandboxStatus,
  onUpdate?: (status: SandboxStatus) => void,
): void {
  onUpdate?.(st)
}

const withEffectiveStatus = withEffectiveSandboxStatus

function noteAlive(projectId: string): void {
  deadObservations.set(projectId, 0)
}

function noteDead(projectId: string): boolean {
  const n = (deadObservations.get(projectId) || 0) + 1
  deadObservations.set(projectId, n)
  return n >= DEAD_OBSERVATIONS_NEEDED
}

function canAutoRecreate(projectId: string): boolean {
  return Date.now() >= (recreateCooldownUntil.get(projectId) || 0)
}

function markRecreated(projectId: string): void {
  recreateCooldownUntil.set(projectId, Date.now() + RECREATE_COOLDOWN_MS)
  deadObservations.set(projectId, 0)
}

function shouldAutoRecreate(projectId: string, status: string, force?: boolean): boolean {
  if (force) return true
  if (!shouldRecreateSandbox(status)) return false
  if (!canAutoRecreate(projectId)) return false
  return noteDead(projectId)
}

/**
 * Ensure a project's sandbox reaches a terminal state (prefer running).
 * Idempotent per projectId while a call is in flight.
 */
export function ensureSandboxRunning(
  projectId: string,
  opts?: EnsureOpts,
): Promise<EnsureSandboxResult> {
  const existing = inflight.get(projectId)
  if (existing && !opts?.forceRecreate) {
    return existing
  }

  const run = doEnsure(projectId, opts).finally(() => {
    if (inflight.get(projectId) === run) {
      inflight.delete(projectId)
    }
  })
  inflight.set(projectId, run)
  return run
}

async function doEnsure(
  projectId: string,
  opts?: EnsureOpts,
): Promise<EnsureSandboxResult> {
  const onUpdate = opts?.onUpdate
  const intervalMs = opts?.intervalMs ?? SANDBOX_POLL_INTERVAL_MS
  const timeoutMs = opts?.timeoutMs ?? SANDBOX_POLL_TIMEOUT_MS

  let st: SandboxStatus
  try {
    st = withEffectiveStatus(await getSandboxStatus(projectId))
  } catch (e) {
    // If status fetch fails entirely, try recreate as last resort when forced
    if (opts?.forceRecreate) {
      try {
        markRecreated(projectId)
        st = await recreateSandbox(projectId)
        applyUpdate(st, onUpdate)
        st = withEffectiveStatus(
          await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs }),
        )
        return {
          status: st,
          action: 'recreate',
          ok: st.status === 'running',
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Sandbox ensure failed'
        const failed: SandboxStatus = {
          project_id: projectId,
          sandbox_name: null,
          status: 'error',
          error: msg,
        }
        applyUpdate(failed, onUpdate)
        return { status: failed, action: 'recreate', ok: false }
      }
    }
    const msg = e instanceof Error ? e.message : 'Failed to read sandbox status'
    const failed: SandboxStatus = {
      project_id: projectId,
      sandbox_name: null,
      status: 'error',
      error: msg,
    }
    applyUpdate(failed, onUpdate)
    return { status: failed, action: 'none', ok: false }
  }

  applyUpdate(st, onUpdate)

  if (st.status === 'running' && !opts?.forceRecreate) {
    noteAlive(projectId)
    return { status: st, action: 'none', ok: true }
  }

  let action: EnsureSandboxResult['action'] = 'poll'

  try {
    if (shouldAutoRecreate(projectId, st.status, opts?.forceRecreate)) {
      action = 'recreate'
      markRecreated(projectId)
      st = await runRecreate(projectId, onUpdate)
    } else if (st.status === 'stopped') {
      action = 'start'
      try {
        st = await startSandbox(projectId)
        applyUpdate(st, onUpdate)
      } catch (startErr) {
        // Missing / dead on agent → recreate (with consecutive/cooldown guards)
        const msg = startErr instanceof Error ? startErr.message : String(startErr)
        if (
          /not found|missing|not running|crashed|409|404/i.test(msg) &&
          shouldAutoRecreate(projectId, 'error', opts?.forceRecreate)
        ) {
          action = 'recreate'
          markRecreated(projectId)
          st = await runRecreate(projectId, onUpdate)
        } else if (!/not found|missing|not running|crashed|409|404/i.test(msg)) {
          throw startErr
        }
      }
    }
    // pending / creating → just poll

    if (st.status === 'running') {
      noteAlive(projectId)
      return { status: st, action, ok: true }
    }

    st = withEffectiveStatus(
      await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs }),
    )

    // Still dead after poll — auto-recreate only after consecutive dead + cooldown
    if (
      st.status !== 'running' &&
      action !== 'recreate' &&
      shouldAutoRecreate(projectId, st.status, false)
    ) {
      action = 'recreate'
      markRecreated(projectId)
      st = await runRecreate(projectId, onUpdate)
      if (st.status !== 'running') {
        st = withEffectiveStatus(
          await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs }),
        )
      }
    }

    if (st.status === 'running') noteAlive(projectId)

    return {
      status: st,
      action,
      ok: st.status === 'running',
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Sandbox ensure failed'
    // Not running / missing on agent during ensure → force recreate once (guarded)
    if (
      action !== 'recreate' &&
      /not found|missing|not running|crashed|409|404/i.test(msg) &&
      shouldAutoRecreate(projectId, 'error', opts?.forceRecreate)
    ) {
      try {
        action = 'recreate'
        markRecreated(projectId)
        st = await runRecreate(projectId, onUpdate)
        if (st.status !== 'running') {
          st = withEffectiveStatus(
            await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs }),
          )
        }
        return { status: st, action, ok: st.status === 'running' }
      } catch (reErr) {
        const reMsg = reErr instanceof Error ? reErr.message : msg
        const failed: SandboxStatus = {
          project_id: projectId,
          sandbox_name: st?.sandbox_name ?? null,
          status: 'error',
          error: reMsg,
          image: st?.image,
          created_at: st?.created_at,
        }
        applyUpdate(failed, onUpdate)
        return { status: failed, action: 'recreate', ok: false }
      }
    }
    const failed: SandboxStatus = {
      project_id: projectId,
      sandbox_name: st?.sandbox_name ?? null,
      status: 'error',
      error: msg,
      image: st?.image,
      created_at: st?.created_at,
    }
    applyUpdate(failed, onUpdate)
    return { status: failed, action, ok: false }
  }
}

async function runRecreate(
  projectId: string,
  onUpdate?: (status: SandboxStatus) => void,
): Promise<SandboxStatus> {
  const st = await recreateSandbox(projectId)
  const next: SandboxStatus = {
    ...st,
    status: st.status === 'running' ? 'running' : 'creating',
  }
  applyUpdate(next, onUpdate)
  return next
}

/** Whether an ensure is currently running for this project. */
export function isEnsureInFlight(projectId: string): boolean {
  return inflight.has(projectId)
}
