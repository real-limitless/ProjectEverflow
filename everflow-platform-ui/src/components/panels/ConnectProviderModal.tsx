import { useEffect, useState } from 'react'
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
  FormSelect,
  FormSelectOption,
} from '@patternfly/react-core'
import { listProviders, setProviderAuth } from '@/lib/opencode/client'
import type { OcProvider } from '@/lib/opencode/types'

interface ConnectProviderModalProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onConnected: () => void
}

export function ConnectProviderModal({
  projectId,
  isOpen,
  onClose,
  onConnected,
}: ConnectProviderModalProps) {
  const [providers, setProviders] = useState<OcProvider[]>([])
  const [providerId, setProviderId] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await listProviders(projectId)
        if (cancelled) return
        const list = data.providers || []
        setProviders(list)
        if (list[0]?.id) setProviderId(list[0].id)
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message)
          // Fallback list when OpenCode catalog is unavailable
          setProviders([
            { id: 'openai', name: 'OpenAI' },
            { id: 'anthropic', name: 'Anthropic' },
            { id: 'xai', name: 'xAI' },
          ])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, projectId])

  const submit = async () => {
    if (!apiKey.trim() || !providerId) return
    setBusy(true)
    setError(null)
    try {
      await setProviderAuth(projectId, providerId, apiKey.trim())
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
          Provider API keys are stored only inside the project sandbox OpenCode process (not in
          Everflow DB).
        </p>
        <Form>
          <FormGroup label="Provider" fieldId="oc-provider">
            <FormSelect
              id="oc-provider"
              value={providerId}
              onChange={(_e, v) => setProviderId(v)}
              aria-label="Provider"
            >
              {(providers.length
                ? providers
                : [
                    { id: 'openai', name: 'OpenAI' },
                    { id: 'anthropic', name: 'Anthropic' },
                    { id: 'xai', name: 'xAI' },
                  ]
              ).map((p) => (
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
          </FormGroup>
          {error ? (
            <p className="pf-v6-c-helper-text pf-m-error" role="alert">
              {error}
            </p>
          ) : null}
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={submit} isDisabled={!apiKey.trim() || busy} isLoading={busy}>
          Connect
        </Button>
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
