import { isDemoMode, type SandboxStatus } from '@/lib/api'
import type { Project } from '@/types/project'

/**
 * Full workbench is only available when the sandbox is live (API projects)
 * and this session has verified status via ensure/status poll.
 */
export function isSandboxWorkbenchReady(
  p: Project | undefined | null,
  verified?: boolean,
): boolean {
  if (!p) return false
  if (!p.fromApi || isDemoMode()) return true
  return p.sandboxStatus === 'running' && Boolean(verified)
}

export function isSandboxBooting(status?: string | null): boolean {
  return status === 'pending' || status === 'creating'
}

/**
 * Agent/runtime statuses that mean the microVM is dead or unusable.
 * After stack restart microsandbox often reports `crashed` while the DB still says `running`.
 */
export function isSandboxDeadStatus(status?: string | null): boolean {
  return (
    status === 'error' ||
    status === 'destroyed' ||
    status === 'unknown' ||
    status === 'crashed' ||
    status === 'failed' ||
    status === 'exited' ||
    !status
  )
}

/** Statuses that need start/recreate rather than only polling. */
export function needsSandboxAction(status?: string | null): boolean {
  return status === 'stopped' || isSandboxDeadStatus(status)
}

/** Statuses that should force recreate (not start/poll). */
export function shouldRecreateSandbox(status?: string | null): boolean {
  return isSandboxDeadStatus(status)
}

/** Polling can stop — running success or a dead/failed terminal state. */
export function isSandboxPollTerminal(status?: string | null): boolean {
  return status === 'running' || isSandboxDeadStatus(status)
}

/**
 * Prefer agent-reported status when the platform row is still "running" but the
 * microVM is dead (common after sandbox-agent restart).
 */
export function effectiveSandboxStatus(st: SandboxStatus): string {
  const top = st.status || ''
  const agentRaw = st.agent && typeof st.agent.status === 'string' ? st.agent.status : null
  const agent = agentRaw?.trim().toLowerCase() || null
  if (agent && agent !== top) {
    // Transitional drain — keep platform running so TabBar/BootGate do not thrash.
    if (top === 'running' && agent === 'draining') {
      return top
    }
    if (top === 'running' && agent !== 'running') {
      return agent
    }
    if (
      shouldRecreateSandbox(agent) &&
      !shouldRecreateSandbox(top) &&
      top !== 'creating' &&
      top !== 'pending'
    ) {
      return agent
    }
  }
  return top
}

/** Return a status object with agent-effective `status` / `error` when they differ. */
export function withEffectiveSandboxStatus(st: SandboxStatus): SandboxStatus {
  const eff = effectiveSandboxStatus(st)
  if (eff === st.status) return st
  const agentErr =
    st.agent && typeof st.agent.error === 'string' ? (st.agent.error as string) : null
  return {
    ...st,
    status: eff,
    error:
      st.error ||
      agentErr ||
      (shouldRecreateSandbox(eff)
        ? `Sandbox is ${eff} on agent; recreating…`
        : st.error),
  }
}
