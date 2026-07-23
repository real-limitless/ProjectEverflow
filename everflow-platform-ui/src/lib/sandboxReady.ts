import { isDemoMode } from '@/lib/api'
import type { Project } from '@/types/project'

/** Full workbench is only available when the sandbox is live (API projects). */
export function isSandboxWorkbenchReady(p: Project | undefined | null): boolean {
  if (!p) return false
  if (!p.fromApi || isDemoMode()) return true
  return p.sandboxStatus === 'running'
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
