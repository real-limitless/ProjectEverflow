import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Spinner } from '@patternfly/react-core'
import CubesIcon from '@patternfly/react-icons/dist/esm/icons/cubes-icon'
import { getProject } from '@/data/projects'
import { ensureSandboxRunning } from '@/lib/ensureSandbox'
import { isSandboxBooting } from '@/lib/sandboxReady'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'

type Phase = 'booting' | 'failed'

export function SandboxBootGate({ projectId }: { projectId: string }) {
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const closeProjectTab = usePlaygroundStore((s) => s.closeProjectTab)
  const p = getProject(projectId)
  void catalogVersion

  const [phase, setPhase] = useState<Phase>(() =>
    p?.sandboxStatus === 'error' || p?.sandboxStatus === 'destroyed' ? 'failed' : 'booting',
  )
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const runIdRef = useRef(0)
  const toastedOkRef = useRef(false)

  const applyStatus = useCallback(
    (st: {
      status: string
      sandbox_name?: string | null
      error?: string | null
      image?: string | null
      created_at?: string | null
    }) => {
      patchProjectSandbox(projectId, {
        sandboxStatus: st.status,
        sandboxName: st.sandbox_name,
        sandboxError: st.error,
        sandboxImage: st.image,
        sandboxCreatedAt: st.created_at,
      })
      if (st.error) setMessage(st.error)
    },
    [patchProjectSandbox, projectId],
  )

  const runEnsure = useCallback(
    async (forceRecreate = false) => {
      const runId = ++runIdRef.current
      setBusy(true)
      setPhase('booting')
      setMessage(null)
      toastedOkRef.current = false

      try {
        const result = await ensureSandboxRunning(projectId, {
          forceRecreate,
          onUpdate: (st) => {
            if (runId !== runIdRef.current) return
            applyStatus(st)
          },
        })
        if (runId !== runIdRef.current) return

        applyStatus(result.status)

        if (result.ok && result.status.status === 'running') {
          if (!toastedOkRef.current) {
            toastedOkRef.current = true
            pushToast('Sandbox ready', { kind: 'success' })
          }
          setPhase('booting')
          setMessage(null)
        } else {
          setPhase('failed')
          setMessage(
            result.status.error ||
              `Sandbox is ${result.status.status || 'not ready'}. Retry to start again.`,
          )
          if (result.status.status === 'error') {
            pushToast(result.status.error || 'Sandbox failed to start', { kind: 'danger' })
          }
        }
      } catch (e) {
        if (runId !== runIdRef.current) return
        const msg = e instanceof Error ? e.message : 'Sandbox failed to start'
        setPhase('failed')
        setMessage(msg)
        patchProjectSandbox(projectId, {
          sandboxStatus: 'error',
          sandboxError: msg,
        })
        pushToast(msg, { kind: 'danger' })
      } finally {
        if (runId === runIdRef.current) setBusy(false)
      }
    },
    [applyStatus, patchProjectSandbox, projectId],
  )

  // Auto-ensure when gate mounts or project changes
  useEffect(() => {
    if (!p?.fromApi) return
    void runEnsure(false)
    return () => {
      runIdRef.current += 1
    }
    // Only re-run when switching projects; Retry calls runEnsure explicitly
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  if (!p) {
    return (
      <div className="project-splash sandbox-boot-gate">
        <div className="project-splash-card">
          <h1 className="project-splash-title">Project not found</h1>
          <p className="project-splash-desc">This project is no longer in the catalog.</p>
          <div className="project-splash-actions">
            <Button variant="secondary" onClick={() => closeProjectTab(projectId)}>
              Close
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const status = p.sandboxStatus || 'pending'
  const booting = phase === 'booting' || busy || isSandboxBooting(status)
  const failed = phase === 'failed' && !busy

  return (
    <div className="project-splash sandbox-boot-gate" role="status" aria-live="polite">
      <div className="project-splash-card">
        <div className="project-splash-icon sandbox-boot-gate-icon" aria-hidden>
          {booting && !failed ? (
            <Spinner size="lg" aria-label="Starting sandbox" />
          ) : (
            <CubesIcon />
          )}
        </div>
        <h1 className="project-splash-title">
          {failed ? 'Sandbox not ready' : 'Starting sandbox'}
        </h1>
        <p className="project-splash-desc">
          {failed
            ? message ||
              'The playground sandbox could not be started. Everything in the workbench runs inside the sandbox.'
            : `Preparing a sandbox for “${p.name}”. The workbench opens when the container is running.`}
        </p>

        <div className="sandbox-boot-meta">
          <span className="sandbox-boot-status" data-status={status}>
            {status}
          </span>
          {p.sandboxName ? (
            <span className="sandbox-boot-name" title={p.sandboxName}>
              {p.sandboxName}
            </span>
          ) : null}
          {p.sandboxImage ? (
            <span className="sandbox-boot-image" title={p.sandboxImage}>
              {p.sandboxImage}
            </span>
          ) : null}
        </div>

        {failed && message ? (
          <p className="sandbox-boot-error" role="alert">
            {message}
          </p>
        ) : null}

        <div className="project-splash-actions">
          {failed ? (
            <Button
              variant="primary"
              isLoading={busy}
              onClick={() => void runEnsure(true)}
            >
              Retry sandbox
            </Button>
          ) : null}
          <Button
            variant={failed ? 'secondary' : 'link'}
            onClick={() => closeProjectTab(projectId)}
            isDisabled={busy && !failed}
          >
            Close project
          </Button>
        </div>
      </div>
    </div>
  )
}
