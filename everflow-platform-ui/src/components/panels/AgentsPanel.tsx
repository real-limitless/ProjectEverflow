import { useMemo, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { FloatingCoachPanel } from '@/components/studio/FloatingCoachPanel'
import { getProject } from '@/data/projects'
import {
  DEFAULT_AGENT_HARNESS_IDS,
  getHarness,
  harnessLaunchCommand,
} from '@/data/harnesses'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'

interface CoachMsg {
  role: 'user' | 'assistant'
  text: string
}

export function AgentsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const setTerminalPrefill = usePlaygroundStore((s) => s.setTerminalPrefill)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const agents = useProjectStudio(projectId).agents
  const createAgent = useStudioDemoStore((s) => s.createAgent)

  const harnesses = useMemo(() => {
    const fromProject = project?.harnesses?.filter((h) => h.enabled) || []
    if (fromProject.length) return fromProject
    return DEFAULT_AGENT_HARNESS_IDS.map((id) => {
      const def = getHarness(id)
      return { id, label: def?.name || id, enabled: true }
    })
  }, [project?.harnesses])

  const [open, setOpen] = useState(false)
  const [coachOpen, setCoachOpen] = useState(true)
  const [name, setName] = useState('')
  const [role, setRole] = useState('general')
  const [desc, setDesc] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [tools, setTools] = useState('file_read, git_status')

  const [coachInput, setCoachInput] = useState('')
  const [coachMsgs, setCoachMsgs] = useState<CoachMsg[]>([
    {
      role: 'assistant',
      text: 'Describe the agent you want (e.g. “review PRs for security”). I’ll draft a name, role, and system prompt you can apply.',
    },
  ])
  const [draft, setDraft] = useState<{
    name: string
    role: string
    desc: string
    systemPrompt: string
  } | null>(null)

  const submit = () => {
    if (!name.trim()) return
    createAgent(projectId, {
      name: name.trim(),
      role,
      desc: desc || 'Custom agent',
      systemPrompt: systemPrompt || `You are ${name.trim()}.`,
      tools: tools
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      active: false,
    })
    pushToast('Agent created', { kind: 'success' })
    setOpen(false)
    setName('')
    setDesc('')
    setSystemPrompt('')
  }

  const launchHarness = (id: string) => {
    const cmd = harnessLaunchCommand(id)
    if (!cmd) {
      pushToast('No CLI mapped for this harness', { kind: 'warning' })
      return
    }
    if (project?.fromApi && project.sandboxStatus !== 'running') {
      pushToast(`Sandbox is ${project.sandboxStatus || 'not ready'}`, { kind: 'warning' })
      return
    }
    openPanelType('terminal')
    setTerminalPrefill(cmd)
    pushToast(`Terminal prefilled with \`${cmd}\``, { kind: 'info' })
  }

  const sendCoach = () => {
    const text = coachInput.trim()
    if (!text) return
    const suggestedName =
      text.length > 40 ? `${text.slice(0, 28).trim()}…` : text.replace(/^./, (c) => c.toUpperCase())
    const suggestedRole = /deploy|review/i.test(text)
      ? 'reviewer'
      : /code|implement|frontend|backend/i.test(text)
        ? 'coder'
        : 'general'
    const prompt = `You are ${suggestedName}, an Everflow project agent.\n\nGoal: ${text}\n\nRules:\n- Prefer project tools over guessing\n- Ask before destructive actions\n- Keep answers concise`
    const nextDraft = {
      name: suggestedName.slice(0, 48),
      role: suggestedRole,
      desc: text.slice(0, 120),
      systemPrompt: prompt,
    }
    setDraft(nextDraft)
    setCoachMsgs((m) => [
      ...m,
      { role: 'user', text },
      {
        role: 'assistant',
        text: `Draft ready:\n• Name: ${nextDraft.name}\n• Role: ${nextDraft.role}\n• Prompt: ${prompt.slice(0, 140)}…\n\nClick Apply to form to fill the create dialog.`,
      },
    ])
    setCoachInput('')
  }

  const applyDraft = () => {
    if (!draft) return
    setName(draft.name)
    setRole(draft.role)
    setDesc(draft.desc)
    setSystemPrompt(draft.systemPrompt)
    setOpen(true)
    pushToast('Coach draft applied', { kind: 'info' })
  }

  return (
    <div className="agents-panel-root">
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          Agents
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <Button variant="secondary" size="sm" onClick={() => setCoachOpen((v) => !v)}>
            {coachOpen ? 'Hide coach' : 'Show coach'}
          </Button>
          <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
            Create agent
          </Button>
        </div>
      </div>

      <div className="panel-scroll">
        <div className="section-label">Sandbox harnesses</div>
        <div className="harness-cards">
          {harnesses.map((h) => {
            const def = getHarness(h.id)
            const cmd = harnessLaunchCommand(h.id)
            return (
              <div key={h.id} className="list-card harness-card">
                <div className="lc-row">
                  <div className="lc-title">{h.label}</div>
                  <Label color="blue" isCompact>
                    {def?.category || 'agent'}
                  </Label>
                </div>
                <div className="lc-meta">{def?.description || 'Runs inside the project sandbox.'}</div>
                {cmd ? (
                  <div style={{ marginTop: 8 }}>
                    <Button size="sm" variant="secondary" onClick={() => launchHarness(h.id)}>
                      Open in Terminal ({cmd})
                    </Button>
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>

        <div className="section-label" style={{ marginTop: 12 }}>
          Studio agents
        </div>
        {agents.length === 0 ? (
          <EmptySplash
            title="No agents yet"
            body="Create an agent or use the floating coach to draft system prompts."
            primaryLabel="Create agent"
            onPrimary={() => setOpen(true)}
          />
        ) : (
          agents.map((a) => (
            <div className="list-card" key={a.id}>
              <div className="lc-row">
                <div className="lc-title">{a.name}</div>
                {a.active ? <Label color="green">active</Label> : <Label color="grey">idle</Label>}
              </div>
              <div className="lc-meta">
                {a.role} · {a.desc}
              </div>
              <div className="lc-meta" style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                {a.systemPrompt.slice(0, 160)}
                {a.systemPrompt.length > 160 ? '…' : ''}
              </div>
            </div>
          ))
        )}
      </div>

      <FloatingCoachPanel
        title="Agent coach"
        open={coachOpen}
        onClose={() => setCoachOpen(false)}
        footer={
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <TextInput
              value={coachInput}
              onChange={(_e, v) => setCoachInput(v)}
              placeholder="What should this agent do?"
              onKeyDown={(e) => {
                if (e.key === 'Enter') sendCoach()
              }}
              aria-label="Coach input"
            />
            <div style={{ display: 'flex', gap: 6 }}>
              <Button size="sm" variant="primary" onClick={sendCoach}>
                Ask
              </Button>
              <Button size="sm" variant="secondary" onClick={applyDraft} isDisabled={!draft}>
                Apply to form
              </Button>
            </div>
          </div>
        }
      >
        {coachMsgs.map((m, i) => (
          <div key={i} className={`coach-msg ${m.role === 'user' ? 'user' : ''}`}>
            {m.text}
          </div>
        ))}
      </FloatingCoachPanel>

      <CreateResourceModal
        isOpen={open}
        title="Create agent"
        onClose={() => setOpen(false)}
        onSubmit={submit}
        isSubmitDisabled={!name.trim()}
      >
        <FormGroup label="Name" isRequired fieldId="ag-name">
          <TextInput id="ag-name" value={name} onChange={(_e, v) => setName(v)} />
        </FormGroup>
        <FormGroup label="Role" fieldId="ag-role">
          <FormSelect id="ag-role" value={role} onChange={(_e, v) => setRole(v)}>
            <FormSelectOption value="general" label="general" />
            <FormSelectOption value="coder" label="coder" />
            <FormSelectOption value="reviewer" label="reviewer" />
            <FormSelectOption value="planner" label="planner" />
          </FormSelect>
        </FormGroup>
        <FormGroup label="Description" fieldId="ag-desc">
          <TextInput id="ag-desc" value={desc} onChange={(_e, v) => setDesc(v)} />
        </FormGroup>
        <FormGroup label="Tools (comma-separated)" fieldId="ag-tools">
          <TextInput id="ag-tools" value={tools} onChange={(_e, v) => setTools(v)} />
        </FormGroup>
        <FormGroup label="System prompt" fieldId="ag-prompt">
          <TextArea
            id="ag-prompt"
            value={systemPrompt}
            onChange={(_e, v) => setSystemPrompt(v)}
            rows={5}
            resizeOrientation="vertical"
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
