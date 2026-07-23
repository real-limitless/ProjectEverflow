import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  FormHelperText,
  FormSelect,
  FormSelectOption,
  Grid,
  GridItem,
  HelperText,
  HelperTextItem,
  Spinner,
  TextInput,
} from '@patternfly/react-core'
import TrashIcon from '@patternfly/react-icons/dist/esm/icons/trash-icon'
import {
  createMyProvider,
  createProjectProvider,
  deleteMyProvider,
  deleteProjectProvider,
  injectProjectProviders,
  listMyProviders,
  listProjectProviders,
  listProviderCatalog,
  type ProviderCatalogItem,
  type ProviderCredential,
  type ProviderName,
} from '@/lib/api'

export type ProvidersScope = 'user' | 'project'

interface ProvidersManagerProps {
  scope: ProvidersScope
  /** Required when scope is project */
  projectId?: string
  lead?: React.ReactNode
}

const FALLBACK_CATALOG: ProviderCatalogItem[] = [
  {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'One key for many chat and embedding models',
    scopes: ['chat', 'embed', 'ocr'],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'Chat, embeddings, and vision models',
    scopes: ['chat', 'embed', 'ocr'],
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude chat and vision models',
    scopes: ['chat', 'ocr'],
  },
  {
    id: 'xai',
    name: 'xAI',
    description: 'Grok models',
    scopes: ['chat'],
  },
]

export function ProvidersManager({ scope, projectId, lead }: ProvidersManagerProps) {
  const [catalog, setCatalog] = useState<ProviderCatalogItem[]>(FALLBACK_CATALOG)
  const [items, setItems] = useState<ProviderCredential[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [provider, setProvider] = useState<ProviderName>('openrouter')
  const [apiKey, setApiKey] = useState('')
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const [cat, list] = await Promise.all([
        listProviderCatalog().catch(() => FALLBACK_CATALOG),
        scope === 'project' && projectId
          ? listProjectProviders(projectId)
          : listMyProviders(),
      ])
      setCatalog(cat.length ? cat : FALLBACK_CATALOG)
      setItems(list)
      if (cat[0]?.id) {
        setProvider((prev) => prev || (cat[0].id as ProviderName))
      }
    } catch (e) {
      setError((e as Error).message || 'Failed to load providers')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [projectId, scope])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const onConnect = async () => {
    if (!apiKey.trim()) return
    if (scope === 'project' && !projectId) {
      setError('No project selected')
      return
    }
    setBusy(true)
    setError('')
    try {
      const payload = {
        provider,
        api_key: apiKey.trim(),
        label: label.trim() || undefined,
      }
      if (scope === 'project' && projectId) {
        await createProjectProvider(projectId, payload)
      } else {
        await createMyProvider(payload)
      }
      // Push vault keys into sandbox when a project context is available
      const injectId = scope === 'project' ? projectId : projectId
      if (injectId) {
        try {
          await injectProjectProviders(injectId)
        } catch {
          /* sandbox may be stopped — vault still saved */
        }
      }
      setApiKey('')
      setLabel('')
      await refresh()
    } catch (e) {
      setError((e as Error).message || 'Could not save provider')
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async (id: string) => {
    setBusy(true)
    setError('')
    try {
      if (scope === 'project' && projectId) {
        await deleteProjectProvider(projectId, id)
      } else {
        await deleteMyProvider(id)
      }
      await refresh()
    } catch (e) {
      setError((e as Error).message || 'Could not remove provider')
    } finally {
      setBusy(false)
    }
  }

  const providerLabel = (id: string) =>
    catalog.find((c) => c.id === id)?.name || id

  return (
    <div className="providers-manager">
      {lead ? <p className="project-settings-lead">{lead}</p> : null}

      {error ? (
        <Alert variant="danger" isInline isPlain title={error} className="project-settings-alert" />
      ) : null}

      {loading ? (
        <div className="providers-manager-loading">
          <Spinner size="lg" aria-label="Loading providers" />
        </div>
      ) : (
        <>
          <section className="providers-manager-list" aria-label="Connected providers">
            {items.length === 0 ? (
              <p className="providers-manager-empty">
                No providers connected yet. Add an API key below so chat, embeddings, and OCR can
                use your models.
              </p>
            ) : (
              <ul className="providers-manager-cards">
                {items.map((item) => (
                  <li key={item.id} className="providers-manager-card">
                    <div className="providers-manager-card-main">
                      <div className="providers-manager-card-title">
                        {providerLabel(item.provider)}
                        {item.label ? (
                          <span className="providers-manager-card-label"> · {item.label}</span>
                        ) : null}
                      </div>
                      <div className="providers-manager-card-meta">
                        Key {item.key_hint || '••••'}
                        {item.scopes?.length ? ` · ${item.scopes.join(', ')}` : ''}
                      </div>
                    </div>
                    <Button
                      variant="plain"
                      aria-label={`Remove ${item.provider}`}
                      icon={<TrashIcon />}
                      isDisabled={busy}
                      onClick={() => void onDelete(item.id)}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Form className="providers-manager-form project-settings-form">
            <Grid hasGutter md={6}>
              <GridItem span={12} md={4}>
                <FormGroup label="Provider" fieldId="prov-id">
                  <FormSelect
                    id="prov-id"
                    value={provider}
                    onChange={(_e, v) => setProvider(v as ProviderName)}
                    aria-label="Provider"
                  >
                    {catalog.map((c) => (
                      <FormSelectOption key={c.id} value={c.id} label={c.name} />
                    ))}
                  </FormSelect>
                </FormGroup>
              </GridItem>
              <GridItem span={12} md={4}>
                <FormGroup label="Label (optional)" fieldId="prov-label">
                  <TextInput
                    id="prov-label"
                    value={label}
                    onChange={(_e, v) => setLabel(v)}
                    placeholder="e.g. Work key"
                  />
                </FormGroup>
              </GridItem>
              <GridItem span={12} md={4}>
                <FormGroup label="API key" fieldId="prov-key" isRequired>
                  <TextInput
                    id="prov-key"
                    type="password"
                    value={apiKey}
                    onChange={(_e, v) => setApiKey(v)}
                    autoComplete="off"
                    aria-label="API key"
                  />
                </FormGroup>
              </GridItem>
              <GridItem span={12}>
                <FormHelperText>
                  <HelperText>
                    <HelperTextItem>
                      Keys are encrypted on the Everflow server. They are never shown again after
                      you save — only a short hint ({items[0]?.key_hint || '••••last4'}).
                    </HelperTextItem>
                  </HelperText>
                </FormHelperText>
                <div className="providers-manager-actions">
                  <Button
                    variant="primary"
                    onClick={() => void onConnect()}
                    isDisabled={!apiKey.trim() || busy}
                    isLoading={busy}
                  >
                    {items.some((i) => i.provider === provider)
                      ? 'Update key'
                      : 'Connect provider'}
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
