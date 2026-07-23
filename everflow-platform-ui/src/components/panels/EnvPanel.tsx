import { useMemo, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  SearchInput,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'

export function EnvPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const openProjectSettings = usePlaygroundStore((s) => s.openProjectSettings)
  const project = getProject(projectId === 'default' ? null : projectId)
  const isApi = Boolean(project?.fromApi)
  const entries = useProjectStudio(projectId).envEntries
  const createEnvEntry = useStudioDemoStore((s) => s.createEnvEntry)
  const deleteEnvEntry = useStudioDemoStore((s) => s.deleteEnvEntry)
  const toggleReveal = useStudioDemoStore((s) => s.toggleReveal)

  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [key, setKey] = useState('')
  const [value, setValue] = useState('')
  const [kind, setKind] = useState<'env' | 'secret'>('env')
  const [attach, setAttach] = useState('')

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return entries
    return entries.filter(
      (e) =>
        e.key.toLowerCase().includes(needle) ||
        e.attachedTo?.some((a) => a.toLowerCase().includes(needle)),
    )
  }, [entries, q])

  const submit = () => {
    if (!key.trim()) return
    createEnvEntry(projectId, {
      key: key.trim(),
      value,
      kind,
      attachedTo: attach
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    })
    pushToast(kind === 'secret' ? 'Secret added' : 'Env var added', { kind: 'success' })
    setKey('')
    setValue('')
    setAttach('')
    setKind('env')
    setOpen(false)
  }

  const displayValue = (e: (typeof entries)[0]) => {
    if (e.kind !== 'secret') return e.value
    if (e.revealed) return e.value
    return '••••••••'
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <SearchInput
          placeholder="Search env & secrets…"
          value={q}
          onChange={(_e, v) => setQ(v)}
          onClear={() => setQ('')}
          style={{ maxWidth: 240 }}
        />
        {!(isApi && entries.length === 0) && (
          <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
            Add
          </Button>
        )}
      </div>
      <div className="panel-scroll">
        <p style={{ fontSize: 12, color: 'var(--pf-t--global--text--color--subtle)', marginTop: 0 }}>
          Environment variables and secrets in one place. Secrets are masked; attach them to services
          or deploy targets.
        </p>
        {filtered.length === 0 ? (
          entries.length === 0 ? (
            isApi ? (
              <EmptySplash
                title="No environment variables"
                body="Add AI provider keys in Project Settings → Providers. Everflow injects them into the sandbox when configured."
                primaryLabel="Open project settings"
                onPrimary={() => openProjectSettings(projectId)}
              />
            ) : (
              <EmptySplash
                title="Nothing configured"
                body="Add environment variables or secrets for this project."
                primaryLabel="Add variable"
                onPrimary={() => setOpen(true)}
              />
            )
          ) : (
            <p className="lc-meta">No entries match your search.</p>
          )
        ) : (
          filtered.map((e) => (
            <div className="list-card" key={e.id}>
              <div className="lc-row">
                <div>
                  <div className="lc-title" style={{ fontFamily: 'var(--mono)' }}>
                    {e.key}{' '}
                    <Label color={e.kind === 'secret' ? 'orange' : 'blue'} isCompact>
                      {e.kind}
                    </Label>
                  </div>
                  <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                    {displayValue(e)}
                  </div>
                  {e.attachedTo && e.attachedTo.length > 0 && (
                    <div className="lc-meta">Attached: {e.attachedTo.join(', ')}</div>
                  )}
                </div>
                <div className="env-row-actions">
                  {e.kind === 'secret' && (
                    <Button variant="link" size="sm" onClick={() => toggleReveal(projectId, e.id)}>
                      {e.revealed ? 'Hide' : 'Reveal'}
                    </Button>
                  )}
                  <Button
                    variant="link"
                    size="sm"
                    onClick={() => {
                      void navigator.clipboard?.writeText(e.value)
                      pushToast('Copied', { kind: 'info' })
                    }}
                  >
                    Copy
                  </Button>
                  <Button
                    variant="link"
                    size="sm"
                    isDanger
                    onClick={() => {
                      deleteEnvEntry(projectId, e.id)
                      pushToast('Removed', { kind: 'warning' })
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      <CreateResourceModal
        isOpen={open}
        title="Add environment entry"
        onClose={() => setOpen(false)}
        onSubmit={submit}
        isSubmitDisabled={!key.trim()}
      >
        <FormGroup label="Key" isRequired fieldId="env-key">
          <TextInput id="env-key" value={key} onChange={(_e, v) => setKey(v)} />
        </FormGroup>
        <FormGroup label="Value" fieldId="env-val">
          <TextInput id="env-val" value={value} onChange={(_e, v) => setValue(v)} type={kind === 'secret' ? 'password' : 'text'} />
        </FormGroup>
        <FormGroup label="Type" fieldId="env-kind">
          <FormSelect id="env-kind" value={kind} onChange={(_e, v) => setKind(v as 'env' | 'secret')}>
            <FormSelectOption value="env" label="Environment variable" />
            <FormSelectOption value="secret" label="Secret" />
          </FormSelect>
        </FormGroup>
        <FormGroup label="Attach to (comma-separated)" fieldId="env-attach">
          <TextInput
            id="env-attach"
            value={attach}
            onChange={(_e, v) => setAttach(v)}
            placeholder="e.g. postgres, billing, edge-01"
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
