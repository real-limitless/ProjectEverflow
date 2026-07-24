import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  TextInput,
} from '@patternfly/react-core'
import {
  ApiError,
  createMyGitCredential,
  createOrgGitCredential,
  deleteMyGitCredential,
  deleteOrgGitCredential,
  listMyGitCredentials,
  listOrgGitCredentials,
  type GitCredential,
} from '@/lib/api'

interface GitCredentialsManagerProps {
  scope: 'user' | 'org'
  orgId?: string
  lead?: ReactNode
  onChanged?: () => void
}

export function GitCredentialsManager({
  scope,
  orgId,
  lead,
  onChanged,
}: GitCredentialsManagerProps) {
  const [rows, setRows] = useState<GitCredential[]>([])
  const [token, setToken] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const data =
        scope === 'org' && orgId
          ? await listOrgGitCredentials(orgId)
          : await listMyGitCredentials()
      setRows(data)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load credentials')
    }
  }, [scope, orgId])

  useEffect(() => {
    void load()
  }, [load])

  const add = async () => {
    if (token.trim().length < 8) {
      setError('Paste a GitHub personal access token (at least 8 characters)')
      return
    }
    setBusy(true)
    setError('')
    try {
      if (scope === 'org' && orgId) {
        await createOrgGitCredential(orgId, {
          token: token.trim(),
          label: label.trim() || undefined,
          is_default: true,
        })
      } else {
        await createMyGitCredential({
          token: token.trim(),
          label: label.trim() || undefined,
          is_default: true,
        })
      }
      setToken('')
      setLabel('')
      await load()
      onChanged?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to save credential')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: string) => {
    setBusy(true)
    setError('')
    try {
      if (scope === 'org' && orgId) await deleteOrgGitCredential(orgId, id)
      else await deleteMyGitCredential(id)
      await load()
      onChanged?.()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to delete credential')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="git-credentials-manager">
      {lead ? <p className="git-credentials-lead">{lead}</p> : null}
      {error ? <Alert variant="danger" title={error} isInline className="auth-alert" /> : null}
      <ul className="git-credentials-list">
        {rows.length === 0 ? (
          <li className="git-credentials-empty">No tokens saved yet.</li>
        ) : (
          rows.map((r) => (
            <li key={r.id}>
              <span>
                {r.label || r.provider} · {r.key_hint}
                {r.is_default ? ' · default' : ''}
              </span>
              <Button variant="link" isDanger isDisabled={busy} onClick={() => void remove(r.id)}>
                Revoke
              </Button>
            </li>
          ))
        )}
      </ul>
      <Form
        onSubmit={(e) => {
          e.preventDefault()
          void add()
        }}
      >
        <FormGroup label="Label" fieldId={`git-label-${scope}`}>
          <TextInput
            id={`git-label-${scope}`}
            value={label}
            onChange={(_e, v) => setLabel(v)}
            placeholder="Personal PAT"
          />
        </FormGroup>
        <FormGroup label="GitHub token" fieldId={`git-token-${scope}`} isRequired>
          <TextInput
            id={`git-token-${scope}`}
            type="password"
            value={token}
            onChange={(_e, v) => setToken(v)}
            placeholder="ghp_… or github_pat_…"
            autoComplete="off"
          />
        </FormGroup>
        <Button
          variant="secondary"
          onClick={() => void add()}
          isLoading={busy}
          isDisabled={busy || token.trim().length < 8}
        >
          Save token
        </Button>
      </Form>
    </div>
  )
}
