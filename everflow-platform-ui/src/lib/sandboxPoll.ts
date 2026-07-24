import { getSandboxStatus, type SandboxStatus } from '@/lib/api'
import { isSandboxPollTerminal, withEffectiveSandboxStatus } from '@/lib/sandboxReady'

/** Default poll interval while waiting for create/start. */
export const SANDBOX_POLL_INTERVAL_MS = 2000

/**
 * Default wait budget. Backend create uses sandbox_agent_timeout_seconds (120s);
 * allow a bit more for slow first boots / named-volume setup.
 */
export const SANDBOX_POLL_TIMEOUT_MS = 150_000

export async function waitForSandbox(
  projectId: string,
  opts?: {
    intervalMs?: number
    timeoutMs?: number
    onUpdate?: (status: SandboxStatus) => void
  },
): Promise<SandboxStatus> {
  const intervalMs = opts?.intervalMs ?? SANDBOX_POLL_INTERVAL_MS
  const timeoutMs = opts?.timeoutMs ?? SANDBOX_POLL_TIMEOUT_MS
  const start = Date.now()

  // First hit immediately
  let last = withEffectiveSandboxStatus(await getSandboxStatus(projectId))
  opts?.onUpdate?.(last)
  if (isSandboxPollTerminal(last.status)) {
    return last
  }

  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, intervalMs))
    last = withEffectiveSandboxStatus(await getSandboxStatus(projectId))
    opts?.onUpdate?.(last)
    if (isSandboxPollTerminal(last.status)) {
      return last
    }
  }
  return last
}
