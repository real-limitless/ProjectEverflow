import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Spinner,
} from '@patternfly/react-core'
import { getProject, updateProjectInCatalog } from '@/data/projects'
import { getProject as apiGetProject } from '@/lib/api'
import { ensureSandboxRunning } from '@/lib/ensureSandbox'
import { isSandboxBooting, shouldRecreateSandbox } from '@/lib/sandboxReady'
import { pushToast } from '@/lib/studioToast'
import { ensureReposCloned, isCloneableUrl, mergeApiProjectRepos } from '@/lib/workspaceRepos'
import { usePlaygroundStore } from '@/store/playgroundStore'

type Phase = 'booting' | 'failed'

export function SandboxBootGate({ projectId }: { projectId: string }) {
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const setSandboxReady = usePlaygroundStore((s) => s.setSandboxReady)
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
      setSandboxReady(projectId, false)

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
          // Sync repos from API (server may have finished clone) then ensure any pending remotes
          try {
            setMessage('Cloning repositories into workspace…')
            let catalog = getProject(projectId)
            try {
              const fresh = await apiGetProject(projectId)
              if (runId !== runIdRef.current) return
              const merged = mergeApiProjectRepos(fresh, catalog?.repos)
              if (merged.length) {
                updateProjectInCatalog(projectId, { repos: merged })
                usePlaygroundStore.setState({
                  catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
                })
                catalog = getProject(projectId)
              }
              applyStatus({
                status: fresh.sandbox_status || result.status.status,
                sandbox_name: fresh.sandbox_name,
                error: fresh.sandbox_error,
                image: fresh.sandbox_image,
                created_at: fresh.sandbox_created_at,
              })
            } catch {
              /* keep local catalog */
            }

            const needsClone = (catalog?.repos || []).some(
              (r) =>
                isCloneableUrl(r.url) &&
                r.cloneStatus !== 'ready' &&
                r.cloneStatus !== 'skipped',
            )
            if (needsClone && catalog?.repos?.length) {
              const cloneResult = await ensureReposCloned(projectId, catalog.repos)
              if (runId !== runIdRef.current) return
              const anyReady = cloneResult.repos.some((r) => r.cloneStatus === 'ready')
              updateProjectInCatalog(projectId, {
                repos: cloneResult.repos,
                // Drop seed file catalog so Code panel walks live sandbox FS
                ...(anyReady || cloneResult.cloned > 0
                  ? { files: [], code: {} }
                  : {}),
              })
              usePlaygroundStore.setState({
                catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
              })
              if (cloneResult.failed > 0) {
                const firstErr = cloneResult.repos.find((r) => r.cloneStatus === 'error')
                pushToast(
                  firstErr?.cloneError?.split('\n')[0] ||
                    `Failed to clone ${cloneResult.failed} repositor${cloneResult.failed === 1 ? 'y' : 'ies'}`,
                  { kind: 'danger' },
                )
              } else if (cloneResult.cloned > 0) {
                pushToast(
                  `Cloned ${cloneResult.cloned} repositor${cloneResult.cloned === 1 ? 'y' : 'ies'} into workspace`,
                  { kind: 'success' },
                )
              }
            }
          } catch (e) {
            if (runId !== runIdRef.current) return
            const msg = e instanceof Error ? e.message : 'Repository clone failed'
            pushToast(msg, { kind: 'warning' })
          }

          if (!toastedOkRef.current) {
            toastedOkRef.current = true
            pushToast('Sandbox ready', { kind: 'success' })
          }
          setPhase('booting')
          setMessage(null)
          setSandboxReady(projectId, true)
        } else {
          setPhase('failed')
          setMessage(
            result.status.error ||
              `Sandbox is ${result.status.status || 'not ready'}. Create a sandbox to open the playground.`,
          )
          setSandboxReady(projectId, false)
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
        setSandboxReady(projectId, false)
        pushToast(msg, { kind: 'danger' })
      } finally {
        if (runId === runIdRef.current) setBusy(false)
      }
    },
    [applyStatus, patchProjectSandbox, projectId, setSandboxReady],
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
      <Modal
        variant={ModalVariant.small}
        isOpen
        onClose={() => closeProjectTab(projectId)}
        aria-labelledby="sandbox-boot-title"
        className="sandbox-boot-modal"
      >
        <ModalHeader title="Project not found" labelId="sandbox-boot-title" />
        <ModalBody>
          <p>This project is no longer in the catalog.</p>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => closeProjectTab(projectId)}>
            Close
          </Button>
        </ModalFooter>
      </Modal>
    )
  }

  const status = p.sandboxStatus || 'pending'
  const booting = phase === 'booting' || busy || isSandboxBooting(status)
  const failed = phase === 'failed' && !busy
  const needsCreate = failed && shouldRecreateSandbox(status)
  const title = failed
    ? 'Sandbox required'
    : 'Starting sandbox'
  const description = failed
    ? message ||
      'The playground runs inside a project sandbox. Create or start a sandbox to continue.'
    : status === 'creating' || status === 'pending'
      ? `Preparing a sandbox for “${p.name}”. Dead or crashed sandboxes are recreated automatically after a stack restart.`
      : `Preparing a sandbox for “${p.name}”. The workbench opens when the container is running.`

  return (
    <>
      <div className="sandbox-boot-host" aria-hidden />
      <Modal
        variant={ModalVariant.small}
        isOpen
        onClose={() => {
          if (!busy) closeProjectTab(projectId)
        }}
        aria-labelledby="sandbox-boot-title"
        className="sandbox-boot-modal"
      >
        <ModalHeader
          title={title}
          labelId="sandbox-boot-title"
          description={
            failed
              ? 'Everything in the playground needs a running sandbox.'
              : undefined
          }
        />
        <ModalBody>
          <div className="sandbox-boot-modal-body" aria-live="polite">
            {booting && !failed ? (
              <div className="sandbox-boot-modal-spinner">
                <Spinner size="lg" aria-label="Starting sandbox" />
              </div>
            ) : null}
            <p className="sandbox-boot-modal-desc">{description}</p>
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
          </div>
        </ModalBody>
        <ModalFooter>
          {failed ? (
            <Button
              variant="primary"
              isLoading={busy}
              onClick={() => void runEnsure(true)}
            >
              {needsCreate ? 'Create sandbox' : 'Retry sandbox'}
            </Button>
          ) : null}
          <Button
            variant={failed ? 'secondary' : 'link'}
            onClick={() => closeProjectTab(projectId)}
            isDisabled={busy && !failed}
          >
            Close project
          </Button>
        </ModalFooter>
      </Modal>
    </>
  )
}
