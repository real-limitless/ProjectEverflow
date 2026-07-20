import { getSandboxStatus, type SandboxStatus } from '@/lib/api'

export async function waitForSandbox(
  projectId: string,
  opts?: {
    intervalMs?: number
    timeoutMs?: number
    onUpdate?: (status: SandboxStatus) => void
  },
): Promise<SandboxStatus> {
  const intervalMs = opts?.intervalMs ?? 2000
  const timeoutMs = opts?.timeoutMs ?? 180_000
  const start = Date.now()

  // First hit immediately
  let last = await getSandboxStatus(projectId)
  opts?.onUpdate?.(last)
  if (last.status === 'running' || last.status === 'error' || last.status === 'destroyed') {
    return last
  }

  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, intervalMs))
    last = await getSandboxStatus(projectId)
    opts?.onUpdate?.(last)
    if (last.status === 'running' || last.status === 'error' || last.status === 'destroyed') {
      return last
    }
  }
  return last
}
