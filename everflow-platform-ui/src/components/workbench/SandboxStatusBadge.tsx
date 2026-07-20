import { useEffect, useState } from 'react'
import { Button, Label, Spinner } from '@patternfly/react-core'
import { getSandboxStatus, isDemoMode, recreateSandbox } from '@/lib/api'
import { waitForSandbox } from '@/lib/sandboxPoll'
import { getProject } from '@/data/projects'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'

const COLOR: Record<string, 'blue' | 'green' | 'orange' | 'red' | 'grey' | 'purple'> = {
  pending: 'blue',
  creating: 'purple',
  running: 'green',
  stopped: 'grey',
  error: 'red',
  destroyed: 'grey',
}

export function SandboxStatusBadge({ projectId }: { projectId: string }) {
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const p = getProject(projectId)
  void catalogVersion

  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    if (!p?.fromApi || isDemoMode()) return
    const status = p.sandboxStatus

    let cancelled = false
    const tick = async () => {
      try {
        const st = await getSandboxStatus(projectId)
        if (cancelled) return
        patchProjectSandbox(projectId, {
          sandboxStatus: st.status,
          sandboxName: st.sandbox_name,
          sandboxError: st.error,
          sandboxImage: st.image,
          sandboxCreatedAt: st.created_at,
        })
      } catch {
        /* ignore */
      }
    }
    void tick()
    // Keep polling while not stable running (includes error → user may recreate)
    const interval =
      status === 'running' ? 15000 : status === 'pending' || status === 'creating' ? 2000 : 5000
    const id = window.setInterval(() => void tick(), interval)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [projectId, p?.fromApi, p?.sandboxStatus, patchProjectSandbox])

  if (!p?.fromApi) return null
  const status = p.sandboxStatus || 'pending'
  const color = COLOR[status] || 'grey'
  const busy = status === 'pending' || status === 'creating'
  const canRecreate = status === 'error' || status === 'destroyed' || status === 'stopped'

  return (
    <span className="sandbox-status-badge" title={p.sandboxError || p.sandboxName || status}>
      {busy ? <Spinner size="sm" aria-label="Sandbox provisioning" /> : null}
      <Label color={color} isCompact>
        sandbox · {status}
      </Label>
      {canRecreate ? (
        <Button
          variant="link"
          isInline
          size="sm"
          isLoading={retrying}
          onClick={async (e) => {
            e.stopPropagation()
            setRetrying(true)
            try {
              await recreateSandbox(projectId)
              patchProjectSandbox(projectId, {
                sandboxStatus: 'creating',
                sandboxError: null,
              })
              pushToast('Sandbox recreate started', { kind: 'info' })
              const st = await waitForSandbox(projectId, {
                onUpdate: (s) => {
                  patchProjectSandbox(projectId, {
                    sandboxStatus: s.status,
                    sandboxName: s.sandbox_name,
                    sandboxError: s.error,
                    sandboxImage: s.image,
                    sandboxCreatedAt: s.created_at,
                  })
                },
              })
              if (st.status === 'running') {
                pushToast('Sandbox ready', { kind: 'success' })
              } else {
                pushToast(st.error || 'Sandbox recreate failed', { kind: 'danger' })
              }
            } catch (err) {
              pushToast(err instanceof Error ? err.message : 'Recreate failed', { kind: 'danger' })
            } finally {
              setRetrying(false)
            }
          }}
        >
          Recreate
        </Button>
      ) : null}
    </span>
  )
}
