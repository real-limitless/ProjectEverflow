import {
  getSandboxStatus,
  recreateSandbox,
  startSandbox,
  type SandboxStatus,
} from '@/lib/api'
import { waitForSandbox } from '@/lib/sandboxPoll'

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

function applyUpdate(
  st: SandboxStatus,
  onUpdate?: (status: SandboxStatus) => void,
): void {
  onUpdate?.(st)
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
  const intervalMs = opts?.intervalMs
  const timeoutMs = opts?.timeoutMs

  let st: SandboxStatus
  try {
    st = await getSandboxStatus(projectId)
  } catch (e) {
    // If status fetch fails entirely, try recreate as last resort when forced
    if (opts?.forceRecreate) {
      try {
        st = await recreateSandbox(projectId)
        applyUpdate(st, onUpdate)
        st = await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs })
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
    return { status: st, action: 'none', ok: true }
  }

  let action: EnsureSandboxResult['action'] = 'poll'

  try {
    if (opts?.forceRecreate || shouldRecreate(st.status)) {
      action = 'recreate'
      st = await recreateSandbox(projectId)
      applyUpdate(
        {
          ...st,
          status: st.status === 'running' ? 'running' : 'creating',
        },
        onUpdate,
      )
    } else if (st.status === 'stopped') {
      action = 'start'
      try {
        st = await startSandbox(projectId)
        applyUpdate(st, onUpdate)
      } catch (startErr) {
        // Missing on agent → recreate
        const msg = startErr instanceof Error ? startErr.message : String(startErr)
        if (/not found|missing|409|404/i.test(msg)) {
          action = 'recreate'
          st = await recreateSandbox(projectId)
          applyUpdate(
            {
              ...st,
              status: st.status === 'running' ? 'running' : 'creating',
            },
            onUpdate,
          )
        } else {
          throw startErr
        }
      }
    }
    // pending / creating → just poll

    if (st.status === 'running') {
      return { status: st, action, ok: true }
    }

    st = await waitForSandbox(projectId, { onUpdate, intervalMs, timeoutMs })
    return {
      status: st,
      action,
      ok: st.status === 'running',
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Sandbox ensure failed'
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

function shouldRecreate(status: string): boolean {
  return status === 'error' || status === 'destroyed' || status === 'unknown' || !status
}

/** Whether an ensure is currently running for this project. */
export function isEnsureInFlight(projectId: string): boolean {
  return inflight.has(projectId)
}
