import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  FormHelperText,
  Grid,
  GridItem,
  HelperText,
  HelperTextItem,
  Label,
  Spinner,
  TextInput,
} from '@patternfly/react-core'
import TrashIcon from '@patternfly/react-icons/dist/esm/icons/trash-icon'
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
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data =
        scope === 'org' && orgId
          ? await listOrgGitCredentials(orgId)
          : await listMyGitCredentials()
      setRows(data)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load credentials')
    } finally {
      setLoading(false)
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

  const listLabel =
    scope === 'org' ? 'Organization Git tokens' : 'Personal Git tokens'

  return (
    <div className="git-credentials-manager">
      {lead ? <p className="project-settings-lead git-credentials-lead">{lead}</p> : null}

      {error ? (
        <Alert
          variant="danger"
          isInline
          isPlain
          title={error}
          className="project-settings-alert"
        />
      ) : null}

      {loading ? (
        <div className="git-credentials-loading">
          <Spinner size="lg" aria-label="Loading Git credentials" />
        </div>
      ) : (
        <>
          <section className="git-credentials-list-section" aria-label={listLabel}>
            {rows.length === 0 ? (
              <p className="git-credentials-empty">
                No tokens saved yet. Add a GitHub personal access token below to clone private
                repositories.
              </p>
            ) : (
              <ul className="git-credentials-cards">
                {rows.map((r) => (
                  <li key={r.id} className="git-credentials-card">
                    <div className="git-credentials-card-main">
                      <div className="git-credentials-card-title">
                        {r.label || r.provider || 'GitHub token'}
                        {r.is_default ? (
                          <Label color="blue" isCompact className="git-credentials-default-chip">
                            Default
                          </Label>
                        ) : null}
                      </div>
                      <div className="git-credentials-card-meta">
                        {r.provider ? `${r.provider} · ` : ''}
                        {r.key_hint || '••••'}
                      </div>
                    </div>
                    <Button
                      variant="plain"
                      aria-label={`Revoke ${r.label || r.provider || 'token'}`}
                      icon={<TrashIcon />}
                      isDisabled={busy}
                      onClick={() => void remove(r.id)}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Form
            className="git-credentials-form project-settings-form"
            onSubmit={(e) => {
              e.preventDefault()
              void add()
            }}
          >
            <Grid hasGutter md={6}>
              <GridItem span={12} md={4}>
                <FormGroup label="Label (optional)" fieldId={`git-label-${scope}`}>
                  <TextInput
                    id={`git-label-${scope}`}
                    value={label}
                    onChange={(_e, v) => setLabel(v)}
                    placeholder={scope === 'org' ? 'Org bot PAT' : 'Personal PAT'}
                  />
                </FormGroup>
              </GridItem>
              <GridItem span={12} md={8}>
                <FormGroup label="GitHub token" fieldId={`git-token-${scope}`} isRequired>
                  <TextInput
                    id={`git-token-${scope}`}
                    type="password"
                    value={token}
                    onChange={(_e, v) => setToken(v)}
                    placeholder="ghp_… or github_pat_…"
                    autoComplete="off"
                    aria-label="GitHub token"
                  />
                </FormGroup>
              </GridItem>
              <GridItem span={12}>
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem>
                      Tokens are stored encrypted on the Everflow server. After you save, only a
                      short hint ({rows[0]?.key_hint || '••••last4'}) is shown — the full secret is
                      never displayed again.
                    </HelperTextItem>
                  </HelperText>
                </FormHelperText>
                <div className="git-credentials-actions">
                  <Button
                    variant="secondary"
                    onClick={() => void add()}
                    isLoading={busy}
                    isDisabled={busy || token.trim().length < 8}
                  >
                    Save token
                  </Button>
                </div>
              </GridItem>
            </Grid>
          </Form>
        </>
      )}
    </div>
  )
}
