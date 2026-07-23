import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  Spinner,
  Tabs,
  Tab,
  TabTitleText,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  agentFromPack,
  agentToPackPayload,
  getOpenCodeHarness,
  isValidAgentSlug,
  OPENCODE_BUILTIN_AGENTS,
  OPENCODE_TOOL_PERMISSIONS,
  putOpenCodeHarness,
  skillFromPack,
  skillToPackPayload,
  slugifyAgentName,
  type OpenCodeHarnessResponse,
} from '@/lib/harness/opencodePack'
import { ensureOpenCode, listAgents, listProviders } from '@/lib/opencode/client'
import type { CatalogItem } from '@/data/chatCatalog'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type {
  AgentDefinition,
  AgentMode,
  AgentPermissionAction,
  McpServerDef,
  SkillDefinition,
} from '@/types/studio'

type SubTab = 'agents' | 'skills'

const PERM_ACTIONS: AgentPermissionAction[] = ['allow', 'ask', 'deny']

const emptyAgentForm = (): AgentDefinition => ({
  id: '',
  name: '',
  description: '',
  desc: '',
  prompt: '',
  systemPrompt: '',
  mode: 'all',
  model: '',
  modelsPreferred: [],
  permission: {
    read: 'allow',
    edit: 'ask',
    bash: 'ask',
    glob: 'allow',
    grep: 'allow',
    webfetch: 'ask',
    websearch: 'ask',
    task: 'deny',
    skill: 'allow',
    question: 'allow',
  },
  mcpIds: [],
  skillAllow: [],
  managed: true,
  source: 'everflow',
  tools: [],
  active: true,
})

function promptOf(a: AgentDefinition): string {
  return a.prompt || a.systemPrompt || ''
}

function descOf(a: AgentDefinition): string {
  return a.description || a.desc || ''
}

export function AgentsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const isApi = Boolean(project?.fromApi)
  const sandboxReady = !isApi || project?.sandboxStatus === 'running'

  const [sub, setSub] = useState<SubTab>('agents')
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pack, setPack] = useState<OpenCodeHarnessResponse | null>(null)
  const [liveAgents, setLiveAgents] = useState<{ name: string; mode?: string; description?: string }[]>(
    [],
  )
  const [models, setModels] = useState<CatalogItem[]>([])

  const [agentOpen, setAgentOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<AgentDefinition>(emptyAgentForm)

  const [skillOpen, setSkillOpen] = useState(false)
  const [skillForm, setSkillForm] = useState<SkillDefinition>({
    id: '',
    name: '',
    description: '',
    body: '',
  })
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null)

  /** Custom agents from the project harness pack (.opencode/agents/) — never demo seeds. */
  const managedAgents: AgentDefinition[] = useMemo(() => {
    if (!isApi || !pack) return []
    return (pack.agents || []).map((a) => agentFromPack(a as Record<string, unknown>))
  }, [isApi, pack])

  const managedSkills: SkillDefinition[] = useMemo(() => {
    if (!pack) return []
    return (pack.skills || []).map((s) => skillFromPack(s as Record<string, unknown>))
  }, [pack])

  const mcpOptions: McpServerDef[] = useMemo(() => {
    if (!pack?.mcp) return []
    return Object.entries(pack.mcp).map(([name, cfg]) => ({
      id: name,
      name,
      transport: String((cfg as { type?: string })?.type || 'remote'),
      endpoint: String(
        (cfg as { url?: string; command?: string })?.url ||
          (Array.isArray((cfg as { command?: string[] }).command)
            ? ((cfg as { command?: string[] }).command || []).join(' ')
            : '') ||
          '',
      ),
      on: (cfg as { enabled?: boolean })?.enabled !== false,
      config: cfg as Record<string, unknown>,
    }))
  }, [pack])

  const packAgentNames = useMemo(
    () => new Set(managedAgents.map((a) => (a.name || a.id).toLowerCase())),
    [managedAgents],
  )

  /** OpenCode-reported agents not already listed as custom pack agents (deduped). */
  const openCodeAgents = useMemo(() => {
    return liveAgents.filter((a) => !packAgentNames.has(a.name.toLowerCase()))
  }, [liveAgents, packAgentNames])

  const agentTabCount = openCodeAgents.length + managedAgents.length

  const load = useCallback(async () => {
    if (!isApi) {
      setPack(null)
      setLiveAgents([])
      setError(null)
      return
    }
    if (!sandboxReady) {
      setPack(null)
      setLiveAgents([])
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      await ensureOpenCode(projectId).catch(() => null)
      // Harness pack is optional for listing live agents; don't hard-fail the panel
      const harnessResult = await getOpenCodeHarness(projectId)
        .then((h) => ({ ok: true as const, harness: h, err: null as string | null }))
        .catch((e: unknown) => ({
          ok: false as const,
          harness: null,
          err: e instanceof Error ? e.message : String(e),
        }))
      const [agents, prov] = await Promise.all([
        listAgents(projectId).catch(() => []),
        listProviders(projectId).catch(() => ({
          providers: [] as { id: string; name?: string; models?: unknown }[],
        })),
      ])
      if (harnessResult.ok && harnessResult.harness) {
        setPack(harnessResult.harness)
        setError(null)
      } else {
        // Empty pack so create/sync still works once backend is reachable
        setPack({
          sandbox_name: projectId,
          agents: [],
          skills: [],
          mcp: {},
          manifest: {},
        })
        setError(
          harnessResult.err
            ? `Harness pack unavailable: ${harnessResult.err}. Built-in agents still load when OpenCode is up.`
            : null,
        )
      }
      setLiveAgents(
        (agents || []).map((a) => ({
          name: a.name,
          mode: a.mode,
          description: a.description,
        })),
      )
      const modelItems: CatalogItem[] = []
      for (const pvd of prov.providers || []) {
        const modelsRaw = pvd.models
        if (Array.isArray(modelsRaw)) {
          for (const m of modelsRaw as { id: string; name?: string }[]) {
            modelItems.push({
              id: `${pvd.id}/${m.id}`,
              label: m.name || m.id,
              description: pvd.name || pvd.id,
            })
          }
        } else if (modelsRaw && typeof modelsRaw === 'object') {
          for (const [mid, meta] of Object.entries(
            modelsRaw as Record<string, { name?: string }>,
          )) {
            modelItems.push({
              id: `${pvd.id}/${mid}`,
              label: meta?.name || mid,
              description: pvd.name || pvd.id,
            })
          }
        }
      }
      setModels(modelItems)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      setPack(null)
    } finally {
      setLoading(false)
    }
  }, [isApi, sandboxReady, projectId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const onHarness = (ev: Event) => {
      const detail = (ev as CustomEvent<{ projectId?: string }>).detail
      if (detail?.projectId && detail.projectId !== projectId) return
      void load()
    }
    window.addEventListener('everflow:harness-updated', onHarness)
    return () => window.removeEventListener('everflow:harness-updated', onHarness)
  }, [load, projectId])

  const openCreateAgent = () => {
    if (!isApi || !sandboxReady) {
      pushToast('Create agents on an API project with a running sandbox (OpenCode harness).', {
        kind: 'warning',
      })
      return
    }
    setEditingId(null)
    setForm(emptyAgentForm())
    setAgentOpen(true)
  }

  const openEditAgent = (a: AgentDefinition) => {
    setEditingId(a.id)
    setForm({
      ...emptyAgentForm(),
      ...a,
      id: a.id,
      name: a.name || a.id,
      description: descOf(a),
      prompt: promptOf(a),
      mode: a.mode || 'all',
      modelsPreferred: a.modelsPreferred || [],
      mcpIds: a.mcpIds || [],
      skillAllow: a.skillAllow || [],
      permission: a.permission || emptyAgentForm().permission,
    })
    setAgentOpen(true)
  }

  const setPerm = (key: string, action: AgentPermissionAction) => {
    setForm((f) => ({
      ...f,
      permission: { ...(f.permission || {}), [key]: action },
    }))
  }

  const toggleMcp = (name: string) => {
    setForm((f) => {
      const cur = new Set(f.mcpIds || [])
      if (cur.has(name)) cur.delete(name)
      else cur.add(name)
      return { ...f, mcpIds: [...cur] }
    })
  }

  const toggleSkillAllow = (name: string) => {
    setForm((f) => {
      const cur = new Set(f.skillAllow || [])
      if (cur.has(name)) cur.delete(name)
      else cur.add(name)
      return { ...f, skillAllow: [...cur] }
    })
  }

  const togglePreferredModel = (modelId: string) => {
    setForm((f) => {
      const cur = new Set(f.modelsPreferred || [])
      if (cur.has(modelId)) cur.delete(modelId)
      else cur.add(modelId)
      return { ...f, modelsPreferred: [...cur] }
    })
  }

  const saveAgent = async () => {
    const slug = slugifyAgentName(form.id || form.name)
    if (!isValidAgentSlug(slug)) {
      pushToast('Agent id must be lowercase letters, numbers, hyphens', { kind: 'danger' })
      return
    }
    const description = (form.description || form.desc || '').trim()
    if (!description) {
      pushToast('Description is required', { kind: 'danger' })
      return
    }
    const payload: AgentDefinition = {
      ...form,
      id: slug,
      name: slug,
      description,
      desc: description,
      prompt: form.prompt || form.systemPrompt || `You are ${slug}.`,
      systemPrompt: form.prompt || form.systemPrompt || `You are ${slug}.`,
    }

    if (!isApi || !sandboxReady) {
      pushToast('Agents require an API project with a running sandbox.', { kind: 'warning' })
      return
    }

    setSyncing(true)
    try {
      // Build permission with MCP wildcards for selected servers
      const permission = { ...(payload.permission || {}) } as Record<
        string,
        AgentPermissionAction | Record<string, AgentPermissionAction>
      >
      for (const mcpName of payload.mcpIds || []) {
        permission[`${mcpName}_*`] = 'allow'
      }
      if (payload.skillAllow && payload.skillAllow.length) {
        const skillMap: Record<string, AgentPermissionAction> = { '*': 'deny' }
        for (const s of payload.skillAllow) {
          skillMap[s] = 'allow'
        }
        permission.skill = skillMap
      }
      const agentBody = agentToPackPayload({ ...payload, permission })

      const res = await putOpenCodeHarness(projectId, {
        agents: [agentBody as unknown as AgentDefinition],
        agent_meta: {
          [slug]: {
            modelsPreferred: payload.modelsPreferred || [],
            mcpIds: payload.mcpIds || [],
          },
        },
      })
      setPack(res)

      // Restart OpenCode so markdown agents are discovered; only notify Chat after ensure succeeds
      let ensured = false
      try {
        await ensureOpenCode(projectId, true)
        const agents = await listAgents(projectId).catch(() => [])
        setLiveAgents(
          (agents || []).map((a) => ({
            name: a.name,
            mode: a.mode,
            description: a.description,
          })),
        )
        ensured = true
      } catch {
        /* ensure failed — pack is saved but Chat refresh waits for a successful ensure */
      }

      pushToast(`Agent “${slug}” synced to OpenCode`, { kind: 'success' })
      setAgentOpen(false)
      if (ensured) {
        window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
      }
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to save agent', { kind: 'danger' })
    } finally {
      setSyncing(false)
    }
  }

  const deleteAgent = async (id: string) => {
    if (!isApi || !sandboxReady) {
      pushToast('Agents require an API project with a running sandbox.', { kind: 'warning' })
      return
    }
    setSyncing(true)
    try {
      const res = await putOpenCodeHarness(projectId, { remove_agents: [id] })
      setPack(res)
      try {
        await ensureOpenCode(projectId, true)
      } catch {
        /* ignore */
      }
      pushToast(`Agent “${id}” removed`, { kind: 'warning' })
      window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to delete agent', { kind: 'danger' })
    } finally {
      setSyncing(false)
    }
  }

  const saveSkill = async () => {
    const slug = slugifyAgentName(skillForm.id || skillForm.name)
    if (!isValidAgentSlug(slug)) {
      pushToast('Skill name must be lowercase letters, numbers, hyphens', { kind: 'danger' })
      return
    }
    if (!skillForm.description.trim()) {
      pushToast('Skill description is required', { kind: 'danger' })
      return
    }
    if (!isApi || !sandboxReady) {
      pushToast('Skills require a running sandbox project', { kind: 'warning' })
      return
    }
    setSyncing(true)
    try {
      const res = await putOpenCodeHarness(projectId, {
        skills: [
          skillToPackPayload({ ...skillForm, id: slug, name: slug }) as unknown as SkillDefinition,
        ],
      })
      setPack(res)
      try {
        await ensureOpenCode(projectId, true)
      } catch {
        /* ignore */
      }
      pushToast(`Skill “${slug}” synced to OpenCode`, { kind: 'success' })
      setSkillOpen(false)
      window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to save skill', { kind: 'danger' })
    } finally {
      setSyncing(false)
    }
  }

  const deleteSkill = async (id: string) => {
    if (!isApi || !sandboxReady) return
    setSyncing(true)
    try {
      const res = await putOpenCodeHarness(projectId, { remove_skills: [id] })
      setPack(res)
      pushToast(`Skill “${id}” removed`, { kind: 'warning' })
      window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to delete skill', { kind: 'danger' })
    } finally {
      setSyncing(false)
    }
  }

  const syncNow = async () => {
    setSyncing(true)
    try {
      await load()
      if (isApi && sandboxReady) {
        await ensureOpenCode(projectId, true)
      }
      pushToast('Harness reloaded', { kind: 'info' })
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="agents-panel-root" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as SubTab)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab
            eventKey="agents"
            title={<TabTitleText>Agents ({agentTabCount})</TabTitleText>}
          />
          <Tab
            eventKey="skills"
            title={<TabTitleText>Skills ({managedSkills.length})</TabTitleText>}
          />
        </Tabs>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {isApi ? (
            <Label color={sandboxReady ? 'green' : 'orange'} isCompact>
              {sandboxReady ? 'sandbox ready' : project?.sandboxStatus || 'no sandbox'}
            </Label>
          ) : (
            <Label color="grey" isCompact>
              offline
            </Label>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void syncNow()}
            isDisabled={syncing || loading || !isApi}
          >
            {syncing || loading ? 'Syncing…' : 'Sync'}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() =>
              sub === 'agents'
                ? openCreateAgent()
                : (setEditingSkillId(null),
                  setSkillForm({ id: '', name: '', description: '', body: '' }),
                  setSkillOpen(true))
            }
            isDisabled={!isApi || !sandboxReady}
          >
            {sub === 'agents' ? 'Create agent' : 'Create skill'}
          </Button>
        </div>
      </div>

      <div className="panel-scroll">
        {error ? (
          <div
            className="list-card"
            style={{
              borderColor: pack
                ? 'var(--pf-t--global--border--color--status--warning--default, #f0ab00)'
                : 'var(--pf-t--global--border--color--status--danger--default, #c9190b)',
            }}
          >
            <div className="lc-title">
              {pack ? 'OpenCode harness warning' : 'Could not load OpenCode harness'}
            </div>
            <div className="lc-meta">{error}</div>
            <Button size="sm" variant="secondary" style={{ marginTop: 8 }} onClick={() => void load()}>
              Retry
            </Button>
          </div>
        ) : null}

        {loading && isApi ? (
          <div style={{ padding: 24, display: 'flex', gap: 8, alignItems: 'center' }}>
            <Spinner size="md" /> Loading agents from OpenCode…
          </div>
        ) : null}

        {sub === 'agents' ? (
          <>
            <div className="section-label">OpenCode agents</div>
            <p className="lc-meta" style={{ marginTop: 0, marginBottom: 12 }}>
              Agents come from OpenCode in the project sandbox. Built-in agents are provided by OpenCode;
              custom agents write to <code>.opencode/agents/</code> and apply when OpenCode starts.
            </p>

            {!isApi ? (
              <EmptySplash
                title="OpenCode agents unavailable"
                body="Open an API-backed project with a running sandbox to load agents from OpenCode."
              />
            ) : !sandboxReady ? (
              <EmptySplash
                title="Sandbox not running"
                body="OpenCode agents appear when the project sandbox is ready."
              />
            ) : loading ? null : (
              <>
                <div className="section-label">Provided by OpenCode</div>
                {openCodeAgents.length === 0 ? (
                  <EmptySplash
                    title="No OpenCode agents yet"
                    body="OpenCode did not report any agents. Use Sync after the sandbox is healthy, or create a custom agent below."
                    primaryLabel="Sync"
                    onPrimary={() => void syncNow()}
                  />
                ) : (
                  openCodeAgents.map((a) => {
                    const isBuiltin = OPENCODE_BUILTIN_AGENTS.has(a.name.toLowerCase())
                    return (
                      <div className="list-card" key={`oc-${a.name}`}>
                        <div className="lc-row">
                          <div className="lc-title">{a.name}</div>
                          <Label color="blue" isCompact>
                            {a.mode || 'primary'}
                          </Label>
                          <Label color={isBuiltin ? 'grey' : 'green'} isCompact>
                            {isBuiltin ? 'built-in' : 'opencode'}
                          </Label>
                        </div>
                        <div className="lc-meta">
                          {a.description ||
                            (isBuiltin
                              ? 'OpenCode built-in agent'
                              : 'Agent reported by OpenCode')}
                        </div>
                      </div>
                    )
                  })
                )}

                <div className="section-label" style={{ marginTop: 12 }}>
                  Custom harness
                </div>
                {managedAgents.length === 0 ? (
                  <EmptySplash
                    title="No custom agents"
                    body="Create an agent with a prompt, model, tools, and MCP servers. It will sync into the OpenCode harness."
                    primaryLabel="Create agent"
                    onPrimary={openCreateAgent}
                  />
                ) : (
                  managedAgents.map((a) => (
                    <div className="list-card" key={a.id}>
                      <div className="lc-row">
                        <div className="lc-title">{a.name || a.id}</div>
                        <Label color="purple" isCompact>
                          {a.mode || 'all'}
                        </Label>
                        {a.model ? (
                          <Label color="green" isCompact>
                            {a.model}
                          </Label>
                        ) : null}
                        <Label color="green" isCompact>
                          synced
                        </Label>
                      </div>
                      <div className="lc-meta">{descOf(a)}</div>
                      <div className="lc-meta" style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                        {promptOf(a).slice(0, 180)}
                        {promptOf(a).length > 180 ? '…' : ''}
                      </div>
                      {a.mcpIds?.length || a.modelsPreferred?.length ? (
                        <div className="lc-meta" style={{ marginTop: 4 }}>
                          {a.mcpIds?.length ? `MCP: ${a.mcpIds.join(', ')}` : null}
                          {a.mcpIds?.length && a.modelsPreferred?.length ? ' · ' : null}
                          {a.modelsPreferred?.length
                            ? `Models: ${a.modelsPreferred.join(', ')}`
                            : null}
                        </div>
                      ) : null}
                      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                        <Button size="sm" variant="secondary" onClick={() => openEditAgent(a)}>
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="link"
                          isDanger
                          onClick={() => void deleteAgent(a.id)}
                          isDisabled={syncing}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))
                )}

                <div className="section-label" style={{ marginTop: 16 }}>
                  MCP servers
                </div>
                <p className="lc-meta" style={{ marginTop: 0 }}>
                  Register MCP servers in the Tools panel, then assign them when creating an agent.
                </p>
                <Button size="sm" variant="link" onClick={() => openPanelType('tools')}>
                  Open Tools panel →
                </Button>
                {mcpOptions.length > 0 ? (
                  <div style={{ marginTop: 8 }}>
                    {mcpOptions.map((m) => (
                      <Label
                        key={m.id}
                        color={m.on ? 'green' : 'grey'}
                        isCompact
                        style={{ marginRight: 6 }}
                      >
                        {m.name}
                      </Label>
                    ))}
                  </div>
                ) : (
                  <div className="lc-meta" style={{ marginTop: 8 }}>
                    No MCP servers in the OpenCode harness yet.
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <>
            <div className="section-label">OpenCode skills</div>
            <p className="lc-meta" style={{ marginTop: 0, marginBottom: 12 }}>
              Skills are on-demand instruction packs (<code>SKILL.md</code>) that agents load via the skill
              tool. Synced to <code>.opencode/skills/</code>.
            </p>
            {managedSkills.length === 0 ? (
              <EmptySplash
                title="No skills yet"
                body="Create a skill pack (name + description + instructions). It will appear to OpenCode agents."
                primaryLabel="Create skill"
                onPrimary={() => {
                  setEditingSkillId(null)
                  setSkillForm({ id: '', name: '', description: '', body: '' })
                  setSkillOpen(true)
                }}
              />
            ) : (
              managedSkills.map((s) => (
                <div className="list-card" key={s.id}>
                  <div className="lc-row">
                    <div className="lc-title">{s.name || s.id}</div>
                    <Label color="green" isCompact>
                      skill
                    </Label>
                  </div>
                  <div className="lc-meta">{s.description}</div>
                  <div className="lc-meta" style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>
                    {s.body.slice(0, 160)}
                    {s.body.length > 160 ? '…' : ''}
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setEditingSkillId(s.id)
                        setSkillForm(s)
                        setSkillOpen(true)
                      }}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="link"
                      isDanger
                      onClick={() => void deleteSkill(s.id)}
                      isDisabled={syncing}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))
            )}
          </>
        )}
      </div>

      <CreateResourceModal
        isOpen={agentOpen}
        title={editingId ? `Edit agent · ${editingId}` : 'Create agent'}
        onClose={() => setAgentOpen(false)}
        onSubmit={() => void saveAgent()}
        isSubmitDisabled={
          syncing ||
          !(form.name || form.id).trim() ||
          !(form.description || form.desc || '').trim()
        }
        submitLabel={syncing ? 'Saving…' : editingId ? 'Save & sync' : 'Create & sync'}
      >
        <FormGroup label="Name (slug)" isRequired fieldId="ag-name">
          <TextInput
            id="ag-name"
            value={form.name || form.id}
            onChange={(_e, v) => {
              const slug = slugifyAgentName(v)
              setForm((f) => ({ ...f, name: v, id: slug }))
            }}
            isDisabled={Boolean(editingId)}
            placeholder="code-reviewer"
          />
          <div className="lc-meta" style={{ marginTop: 4 }}>
            OpenCode id: <code>{slugifyAgentName(form.name || form.id || '…')}</code>
          </div>
        </FormGroup>
        <FormGroup label="Description" isRequired fieldId="ag-desc">
          <TextInput
            id="ag-desc"
            value={form.description || form.desc || ''}
            onChange={(_e, v) => setForm((f) => ({ ...f, description: v, desc: v }))}
            placeholder="When to use this agent"
          />
        </FormGroup>
        <FormGroup label="Mode" fieldId="ag-mode">
          <FormSelect
            id="ag-mode"
            value={form.mode || 'all'}
            onChange={(_e, v) => setForm((f) => ({ ...f, mode: v as AgentMode }))}
          >
            <FormSelectOption value="primary" label="primary (Tab-switchable main agent)" />
            <FormSelectOption value="subagent" label="subagent (@ mention / task)" />
            <FormSelectOption value="all" label="all" />
          </FormSelect>
        </FormGroup>
        <FormGroup label="Primary model" fieldId="ag-model">
          <FormSelect
            id="ag-model"
            value={form.model || ''}
            onChange={(_e, v) => setForm((f) => ({ ...f, model: v }))}
          >
            <FormSelectOption value="" label="(inherit session / default)" />
            {models.map((m) => (
              <FormSelectOption key={m.id} value={m.id} label={`${m.label} · ${m.description || ''}`} />
            ))}
          </FormSelect>
        </FormGroup>
        {models.length > 0 ? (
          <FormGroup label="Preferred models (Chat picker)" fieldId="ag-models-pref">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflow: 'auto' }}>
              {models.map((m) => (
                <Checkbox
                  key={m.id}
                  id={`pref-${m.id}`}
                  label={`${m.label} (${m.id})`}
                  isChecked={(form.modelsPreferred || []).includes(m.id)}
                  onChange={() => togglePreferredModel(m.id)}
                />
              ))}
            </div>
          </FormGroup>
        ) : null}
        <FormGroup label="System prompt" isRequired fieldId="ag-prompt">
          <TextArea
            id="ag-prompt"
            value={form.prompt || form.systemPrompt || ''}
            onChange={(_e, v) => setForm((f) => ({ ...f, prompt: v, systemPrompt: v }))}
            rows={6}
            resizeOrientation="vertical"
            placeholder="You are a specialized agent that…"
          />
        </FormGroup>
        <FormGroup label="Tool permissions" fieldId="ag-perms">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {OPENCODE_TOOL_PERMISSIONS.map((t) => (
              <div
                key={t.id}
                style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
              >
                <span style={{ minWidth: 120, fontSize: 13 }}>{t.label}</span>
                <FormSelect
                  id={`perm-${t.id}`}
                  value={
                    typeof form.permission?.[t.id] === 'string'
                      ? (form.permission[t.id] as string)
                      : 'allow'
                  }
                  onChange={(_e, v) => setPerm(t.id, v as AgentPermissionAction)}
                  style={{ maxWidth: 140 }}
                  aria-label={`${t.label} permission`}
                >
                  {PERM_ACTIONS.map((p) => (
                    <FormSelectOption key={p} value={p} label={p} />
                  ))}
                </FormSelect>
                <span className="lc-meta">{t.description}</span>
              </div>
            ))}
          </div>
        </FormGroup>
        <FormGroup label="MCP servers" fieldId="ag-mcp">
          {mcpOptions.length === 0 ? (
            <div className="lc-meta">
              No MCP servers registered.{' '}
              <Button variant="link" isInline onClick={() => openPanelType('tools')}>
                Add in Tools
              </Button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {mcpOptions.map((m) => (
                <Checkbox
                  key={m.id}
                  id={`mcp-${m.id}`}
                  label={`${m.name} (${m.transport})`}
                  isChecked={(form.mcpIds || []).includes(m.name) || (form.mcpIds || []).includes(m.id)}
                  onChange={() => toggleMcp(m.name)}
                />
              ))}
            </div>
          )}
        </FormGroup>
        {managedSkills.length > 0 ? (
          <FormGroup label="Skills allowed" fieldId="ag-skills">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {managedSkills.map((s) => (
                <Checkbox
                  key={s.id}
                  id={`skill-allow-${s.id}`}
                  label={s.name || s.id}
                  isChecked={(form.skillAllow || []).includes(s.id)}
                  onChange={() => toggleSkillAllow(s.id)}
                />
              ))}
            </div>
          </FormGroup>
        ) : null}
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={skillOpen}
        title={editingSkillId ? `Edit skill · ${editingSkillId}` : 'Create skill'}
        onClose={() => setSkillOpen(false)}
        onSubmit={() => void saveSkill()}
        isSubmitDisabled={syncing || !(skillForm.name || skillForm.id).trim() || !skillForm.description.trim()}
        submitLabel={syncing ? 'Saving…' : 'Save & sync'}
      >
        <FormGroup label="Name" isRequired fieldId="sk-name">
          <TextInput
            id="sk-name"
            value={skillForm.name || skillForm.id}
            onChange={(_e, v) =>
              setSkillForm((f) => ({ ...f, name: v, id: slugifyAgentName(v) }))
            }
            isDisabled={Boolean(editingSkillId)}
            placeholder="pr-review"
          />
        </FormGroup>
        <FormGroup label="Description" isRequired fieldId="sk-desc">
          <TextInput
            id="sk-desc"
            value={skillForm.description}
            onChange={(_e, v) => setSkillForm((f) => ({ ...f, description: v }))}
            placeholder="When should the agent load this skill?"
          />
        </FormGroup>
        <FormGroup label="Instructions (SKILL.md body)" fieldId="sk-body">
          <TextArea
            id="sk-body"
            value={skillForm.body}
            onChange={(_e, v) => setSkillForm((f) => ({ ...f, body: v }))}
            rows={8}
            resizeOrientation="vertical"
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
