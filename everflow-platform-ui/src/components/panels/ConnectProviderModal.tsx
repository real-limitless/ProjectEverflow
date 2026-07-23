import { useEffect, useState } from 'react'
import {
  Button,
  Form,
  FormGroup,
  FormHelperText,
  FormSelect,
  FormSelectOption,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextInput,
} from '@patternfly/react-core'
import {
  createMyProvider,
  createProjectProvider,
  injectProjectProviders,
  listProviderCatalog,
  type ProviderName,
} from '@/lib/api'
import { listProviders, setProviderAuth } from '@/lib/opencode/client'
import type { OcProvider } from '@/lib/opencode/types'

interface ConnectProviderModalProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onConnected: () => void
  /** Allow skipping key entry — OpenCode free models may already work. */
  onContinueWithoutKey?: () => void
  continueLabel?: string
}

const FALLBACK: OcProvider[] = [
  { id: 'openrouter', name: 'OpenRouter' },
  { id: 'openai', name: 'OpenAI' },
  { id: 'anthropic', name: 'Anthropic' },
  { id: 'xai', name: 'xAI' },
]

export function ConnectProviderModal({
  projectId,
  isOpen,
  onClose,
  onConnected,
  onContinueWithoutKey,
  continueLabel = 'Continue without key',
}: ConnectProviderModalProps) {
  const [providers, setProviders] = useState<OcProvider[]>(FALLBACK)
  const [providerId, setProviderId] = useState<string>('openrouter')
  const [apiKey, setApiKey] = useState('')
  const [scope, setScope] = useState<'project' | 'account'>('project')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    ;(async () => {
      try {
        const [vaultCat, oc] = await Promise.all([
          listProviderCatalog().catch(() => []),
          listProviders(projectId).catch(() => null),
        ])
        if (cancelled) return

        const fromVault = (vaultCat || [])
          .filter((c) => c.id !== 'custom')
          .map((c) => ({ id: c.id, name: c.name }))
        const fromOc = oc?.providers || []
        const byId = new Map<string, OcProvider>()
        for (const p of [...fromVault, ...fromOc, ...FALLBACK]) {
          if (p?.id) byId.set(p.id, { id: p.id, name: p.name || p.id })
        }
        const list = Array.from(byId.values())
        setProviders(list.length ? list : FALLBACK)
        if (!byId.has(providerId) && list[0]?.id) {
          setProviderId(list[0].id)
        }
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message)
          setProviders(FALLBACK)
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only refresh catalog when modal opens
  }, [isOpen, projectId])

  const submit = async () => {
    if (!apiKey.trim() || !providerId) return
    setBusy(true)
    setError(null)
    const key = apiKey.trim()
    const provider = providerId as ProviderName
    try {
      // 1) Persist in Everflow vault (source of truth)
      if (scope === 'account') {
        await createMyProvider({ provider, api_key: key })
      } else {
        await createProjectProvider(projectId, { provider, api_key: key })
      }

      // 2) Inject all vault keys into the sandbox (env file + OpenCode when up)
      try {
        await injectProjectProviders(projectId)
      } catch {
        /* sandbox may be down; vault still saved */
      }

      // 3) Best-effort live OpenCode auth with the key just entered
      try {
        await setProviderAuth(projectId, providerId, key)
      } catch {
        /* OpenCode may not be ready; inject + ensure will re-apply later */
      }

      setApiKey('')
      onConnected()
      onClose()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={onClose}
      aria-label="Connect LLM provider"
    >
      <ModalHeader title="Connect provider" />
      <ModalBody>
        <p style={{ marginBottom: 12 }}>
          Optional: add a paid provider key for more models. OpenCode also ships free / built-in
          models (e.g. Big Pickle, Nemotron) that work without a key. API keys are encrypted in
          Everflow and injected into this project’s sandbox.
        </p>
        <Form>
          <FormGroup label="Save to" fieldId="oc-scope">
            <FormSelect
              id="oc-scope"
              value={scope}
              onChange={(_e, v) => setScope(v as 'project' | 'account')}
              aria-label="Save scope"
            >
              <FormSelectOption
                value="project"
                label="This project (overrides account for this sandbox)"
              />
              <FormSelectOption
                value="account"
                label="My account (default for all projects)"
              />
            </FormSelect>
          </FormGroup>
          <FormGroup label="Provider" fieldId="oc-provider">
            <FormSelect
              id="oc-provider"
              value={providerId}
              onChange={(_e, v) => setProviderId(v)}
              aria-label="Provider"
            >
              {providers.map((p) => (
                <FormSelectOption key={p.id} value={p.id} label={p.name || p.id} />
              ))}
            </FormSelect>
          </FormGroup>
          <FormGroup label="API key" isRequired fieldId="oc-key">
            <TextInput
              id="oc-key"
              type="password"
              value={apiKey}
              onChange={(_e, v) => setApiKey(v)}
              autoComplete="off"
            />
            <FormHelperText>
              <HelperText>
                <HelperTextItem>
                  Include OpenRouter, OpenAI, Anthropic, or xAI. Keys are never shown again after
                  save.
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          </FormGroup>
          {error ? (
            <p className="pf-v6-c-helper-text pf-m-error" role="alert">
              {error}
            </p>
          ) : null}
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={() => void submit()}
          isDisabled={!apiKey.trim() || busy}
          isLoading={busy}
        >
          Connect
        </Button>
        {onContinueWithoutKey ? (
          <Button
            variant="secondary"
            onClick={() => {
              onContinueWithoutKey()
              onClose()
            }}
            isDisabled={busy}
          >
            {continueLabel}
          </Button>
        ) : null}
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
