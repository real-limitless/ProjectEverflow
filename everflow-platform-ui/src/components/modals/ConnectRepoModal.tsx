import { useState } from 'react'
import {
  Button,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextInput,
} from '@patternfly/react-core'
import { GitCredentialsManager } from '@/components/git/GitCredentialsManager'
import { getProject, updateProjectInCatalog } from '@/data/projects'
import { pathHintFromLabel } from '@/lib/workspaceGit'
import {
  ensureReposCloned,
  isCloneableUrl,
  normalizeReposForCreate,
} from '@/lib/workspaceRepos'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { ProjectRepo } from '@/types/project'

function needsGitCredential(message: string): boolean {
  const low = message.toLowerCase()
  return (
    low.includes('github token') ||
    low.includes('authentication') ||
    low.includes('could not read username') ||
    low.includes('403')
  )
}

export function ConnectRepoModal() {
  const isOpen = usePlaygroundStore((s) => s.connectRepoModal)
  const setOpen = usePlaygroundStore((s) => s.setConnectRepoModal)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const [url, setUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showCreds, setShowCreds] = useState(false)

  const close = () => {
    setOpen(false)
    setUrl('')
    setBranch('main')
    setError('')
    setBusy(false)
    setShowCreds(false)
  }

  const connect = async () => {
    const trimmed = url.trim()
    if (!trimmed) {
      setError('Enter a repository URL')
      return
    }
    if (!isCloneableUrl(trimmed)) {
      setError('URL must start with https://, http://, git@, or ssh://')
      return
    }
    if (!currentProjectId) {
      setError('No project open')
      return
    }
    const p = getProject(currentProjectId)
    if (!p) {
      setError('Project not found')
      return
    }

    const label = pathHintFromLabel(trimmed) || `repo-${p.repos.length + 1}`
    // Every remote gets its own directory under /workspace/<name>/
    const newRepo: ProjectRepo = {
      id: `repo-${Date.now()}`,
      label,
      url: trimmed,
      branch: branch.trim() || 'main',
      provider: 'github',
      active: true,
      localPath: label,
      cloneStatus: 'pending',
    }

    // Drop empty URL placeholders (e.g. default "slug/app" from blank create)
    const kept = p.repos.filter((r) => isCloneableUrl(r.url) || (r.url && r.url.trim()))
    const nextRepos = normalizeReposForCreate([
      ...kept.map((r) => ({ ...r, active: false })),
      { ...newRepo, active: true },
    ])

    updateProjectInCatalog(currentProjectId, { repos: nextRepos })
    usePlaygroundStore.setState({
      catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
      activeRepoByProject: {
        ...usePlaygroundStore.getState().activeRepoByProject,
        [currentProjectId]: newRepo.id,
      },
    })

    // Persist remotes on the API so provision/recreate can re-clone
    if (p.fromApi) {
      setBusy(true)
      setError('')
      try {
        const { apiFetch } = await import('@/lib/api')
        const { projectReposToApiPayload } = await import('@/lib/workspaceRepos')
        await apiFetch(`/api/v1/projects/${currentProjectId}`, {
          method: 'PATCH',
          body: JSON.stringify({ repos: projectReposToApiPayload(nextRepos) }),
        })
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to save repository on server'
        // Still try local clone; warn about persistence
        pushToast(msg, { kind: 'warning' })
      }
    }

    if (p.fromApi && p.sandboxStatus === 'running') {
      setBusy(true)
      setError('')
      try {
        const result = await ensureReposCloned(currentProjectId, nextRepos)
        updateProjectInCatalog(currentProjectId, {
          repos: result.repos,
          // Clear seed file list so Code panel reloads from sandbox FS
          files: result.cloned > 0 || result.repos.some((r) => r.cloneStatus === 'ready') ? [] : p.files,
          code:
            result.cloned > 0 || result.repos.some((r) => r.cloneStatus === 'ready')
              ? {}
              : p.code,
        })
        usePlaygroundStore.setState({
          catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
        })
        if (result.failed > 0) {
          const first = result.repos.find((r) => r.cloneStatus === 'error')
          const errMsg = first?.cloneError || 'Clone failed'
          pushToast(errMsg.split('\n')[0] || 'Clone failed', { kind: 'danger' })
          setError(errMsg)
          if (needsGitCredential(errMsg)) setShowCreds(true)
          setBusy(false)
          return
        }
        pushToast(`Cloned ${label} into workspace`, { kind: 'success' })
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Clone failed'
        setError(msg)
        pushToast(msg, { kind: 'danger' })
        setBusy(false)
        return
      }
      setBusy(false)
    } else if (p.fromApi) {
      pushToast('Repository saved — it will clone when the sandbox is running', { kind: 'info' })
    } else {
      pushToast('Repository attached (demo mode — not cloned to a sandbox)', { kind: 'info' })
    }
    close()
  }

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={close}
      aria-labelledby="connectModalTitle"
    >
      <ModalHeader title="Connect a repository" labelId="connectModalTitle" />
      <ModalBody>
        <Form>
          <FormGroup label="Repository URL" fieldId="repoUrl" isRequired>
            <TextInput
              id="repoUrl"
              value={url}
              onChange={(_e, v) => {
                setUrl(v)
                if (error) setError('')
              }}
              placeholder="https://github.com/you/awesome-app.git"
            />
          </FormGroup>
          <FormGroup label="Branch" fieldId="repoBranch">
            <TextInput
              id="repoBranch"
              value={branch}
              onChange={(_e, v) => setBranch(v)}
              placeholder="main"
            />
          </FormGroup>
          {error ? (
            <p role="alert" style={{ color: 'var(--pf-t--global--text--color--status--danger--default)', fontSize: 13 }}>
              {error}
            </p>
          ) : (
            <p style={{ fontSize: 12, opacity: 0.8, margin: 0 }}>
              HTTPS remotes are cloned into the project sandbox. Private repos need a GitHub PAT
              under Organization & Git settings.
            </p>
          )}
          {showCreds ? (
            <div style={{ marginTop: 12 }}>
              <GitCredentialsManager
                scope="user"
                lead="Add a GitHub personal access token with repo scope, then Connect again."
              />
            </div>
          ) : null}
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={() => void connect()} isLoading={busy} isDisabled={busy}>
          {busy ? 'Cloning…' : 'Connect'}
        </Button>
        <Button variant="link" onClick={close} isDisabled={busy}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
