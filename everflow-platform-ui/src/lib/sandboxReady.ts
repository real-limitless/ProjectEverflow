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

/** Statuses that need start/recreate rather than only polling. */
export function needsSandboxAction(status?: string | null): boolean {
  return (
    status === 'stopped' ||
    status === 'error' ||
    status === 'destroyed' ||
    status === 'unknown' ||
    !status
  )
}
