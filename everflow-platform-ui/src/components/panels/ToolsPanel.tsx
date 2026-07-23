import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  Switch,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import PlugIcon from '@patternfly/react-icons/dist/esm/icons/plug-icon'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  getOpenCodeHarness,
  putOpenCodeHarness,
  slugifyAgentName,
} from '@/lib/harness/opencodePack'
import { ensureOpenCode, listMcp } from '@/lib/opencode/client'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { McpServerDef } from '@/types/studio'

function mcpConfigFromForm(
  name: string,
  transport: string,
  endpoint: string,
  enabled: boolean,
): Record<string, unknown> {
  const isStdio = transport.toLowerCase().includes('stdio')
  if (isStdio) {
    const parts = endpoint.trim().split(/\s+/).filter(Boolean)
    return {
      type: 'local',
      command: parts.length ? parts : ['npx', '-y', name],
      enabled,
    }
  }
  return {
    type: 'remote',
    url: endpoint || `https://mcp.example.com/${name}`,
    enabled,
  }
}

export function ToolsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const project = getProject(projectId === 'default' ? null : projectId)
  const isApi = Boolean(project?.fromApi)
  const sandboxReady = !isApi || project?.sandboxStatus === 'running'

  const studio = useProjectStudio(projectId)
  const httpTools = studio.httpTools
  const localMcps = studio.mcps
  const createTool = useStudioDemoStore((s) => s.createTool)
  const deleteTool = useStudioDemoStore((s) => s.deleteTool)
  const createMcp = useStudioDemoStore((s) => s.createMcp)
  const deleteMcp = useStudioDemoStore((s) => s.deleteMcp)
  const toggleTool = useStudioDemoStore((s) => s.toggleTool)
  const toggleMcp = useStudioDemoStore((s) => s.toggleMcp)

  const [sub, setSub] = useState<'tools' | 'mcps'>('tools')
  const [toolOpen, setToolOpen] = useState(false)
  const [mcpOpen, setMcpOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [liveMcp, setLiveMcp] = useState<McpServerDef[] | null>(null)

  const [toolName, setToolName] = useState('')
  const [method, setMethod] = useState('GET')
  const [url, setUrl] = useState('')

  const [mcpName, setMcpName] = useState('')
  const [transport, setTransport] = useState('HTTP/SSE')
  const [endpoint, setEndpoint] = useState('')

  const refreshLiveMcp = useCallback(async () => {
    if (!isApi || !sandboxReady) {
      setLiveMcp(null)
      return
    }
    try {
      const [harness, statusMap] = await Promise.all([
        getOpenCodeHarness(projectId).catch(() => null),
        listMcp(projectId).catch(() => ({})),
      ])
      const fromPack = Object.entries(harness?.mcp || {}).map(([name, cfg]) => {
        const c = cfg as Record<string, unknown>
        return {
          id: name,
          name,
          transport: String(c.type || 'remote'),
          endpoint: String(
            c.url ||
              (Array.isArray(c.command) ? (c.command as string[]).join(' ') : '') ||
              '',
          ),
          on: c.enabled !== false,
          config: c,
          status: (statusMap as Record<string, { status?: string }>)[name]?.status,
        } satisfies McpServerDef
      })
      // Include status-only entries not yet in pack
      for (const [name, st] of Object.entries(statusMap || {})) {
        if (!fromPack.some((m) => m.name === name)) {
          fromPack.push({
            id: name,
            name,
            transport: 'remote',
            endpoint: '',
            on: true,
            config: {},
            status: (st as { status?: string })?.status,
          })
        }
      }
      setLiveMcp(fromPack)
    } catch {
      setLiveMcp(null)
    }
  }, [isApi, sandboxReady, projectId])

  useEffect(() => {
    void refreshLiveMcp()
  }, [refreshLiveMcp])

  useEffect(() => {
    const onHarness = (ev: Event) => {
      const detail = (ev as CustomEvent<{ projectId?: string }>).detail
      if (detail?.projectId && detail.projectId !== projectId) return
      void refreshLiveMcp()
    }
    window.addEventListener('everflow:harness-updated', onHarness)
    return () => window.removeEventListener('everflow:harness-updated', onHarness)
  }, [projectId, refreshLiveMcp])

  const mcps = liveMcp && liveMcp.length > 0 ? liveMcp : localMcps
  const empty = httpTools.length === 0 && mcps.length === 0

  const syncMcpToOpenCode = async (
    name: string,
    transportVal: string,
    endpointVal: string,
    enabled: boolean,
  ) => {
    if (!isApi || !sandboxReady) return false
    setSyncing(true)
    try {
      await putOpenCodeHarness(projectId, {
        mcp: {
          [name]: mcpConfigFromForm(name, transportVal, endpointVal, enabled),
        },
      })
      try {
        await ensureOpenCode(projectId, true)
      } catch {
        /* optional restart */
      }
      await refreshLiveMcp()
      window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
      return true
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to sync MCP to OpenCode', {
        kind: 'danger',
      })
      return false
    } finally {
      setSyncing(false)
    }
  }

  const handleCreateMcp = async () => {
    if (!mcpName.trim()) return
    const name = slugifyAgentName(mcpName.trim())
    const ep = endpoint || 'https://mcp.example.com/sse'
    createMcp(projectId, {
      name,
      transport,
      endpoint: ep,
      on: true,
    })
    if (isApi && sandboxReady) {
      const ok = await syncMcpToOpenCode(name, transport, ep, true)
      if (ok) pushToast(`MCP “${name}” synced to OpenCode`, { kind: 'success' })
    } else {
      pushToast('MCP server created (local demo)', { kind: 'success' })
    }
    setMcpName('')
    setEndpoint('')
    setMcpOpen(false)
  }

  const handleToggleMcp = async (m: McpServerDef) => {
    toggleMcp(projectId, m.id)
    if (isApi && sandboxReady) {
      await syncMcpToOpenCode(m.name, m.transport, m.endpoint, !m.on)
    }
  }

  const handleDeleteMcp = async (m: McpServerDef) => {
    deleteMcp(projectId, m.id)
    if (isApi && sandboxReady) {
      setSyncing(true)
      try {
        // Disable rather than fully remove unknown structure
        await putOpenCodeHarness(projectId, {
          mcp: {
            [m.name]: { enabled: false },
          },
        })
        await refreshLiveMcp()
        window.dispatchEvent(
          new CustomEvent('everflow:harness-updated', { detail: { projectId } }),
        )
        pushToast('MCP disabled in OpenCode', { kind: 'warning' })
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Failed to update MCP', { kind: 'danger' })
      } finally {
        setSyncing(false)
      }
    } else {
      pushToast('MCP deleted', { kind: 'warning' })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="tools" title={<TabTitleText>Tools ({httpTools.length})</TabTitleText>} />
          <Tab eventKey="mcps" title={<TabTitleText>MCP servers ({mcps.length})</TabTitleText>} />
        </Tabs>
        <Button
          variant="primary"
          size="sm"
          onClick={() => (sub === 'tools' ? setToolOpen(true) : setMcpOpen(true))}
          isDisabled={syncing}
        >
          {sub === 'tools' ? 'Create tool' : 'Create MCP'}
        </Button>
      </div>
      <div className="panel-scroll">
        {sub === 'mcps' && isApi ? (
          <p className="lc-meta" style={{ marginTop: 0 }}>
            MCP servers sync into the project sandbox <code>opencode.json</code> and are available to
            OpenCode agents. Assign them per-agent in the Agents panel.
          </p>
        ) : null}
        {empty ? (
          <EmptySplash
            title="No tools or MCP servers"
            body="Register HTTP tools and MCP servers so agents and chat can call them."
            primaryLabel="Create tool"
            onPrimary={() => setToolOpen(true)}
            secondaryLabel="Create MCP server"
            onSecondary={() => setMcpOpen(true)}
            icon={PlugIcon}
          />
        ) : sub === 'tools' ? (
          httpTools.length === 0 ? (
            <EmptySplash
              title="No HTTP tools"
              body="Create a tool to expose an HTTP action to agents."
              primaryLabel="Create tool"
              onPrimary={() => setToolOpen(true)}
            />
          ) : (
            httpTools.map((t) => (
              <div className="list-card" key={t.id}>
                <div className="lc-row">
                  <div>
                    <div className="lc-title" style={{ fontFamily: 'var(--mono)' }}>
                      {t.name}
                    </div>
                    <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                      {t.method} {t.url}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Label color={t.on ? 'green' : 'grey'}>{t.method}</Label>
                    <Switch
                      id={`tool-${t.id}`}
                      isChecked={t.on}
                      onChange={() => toggleTool(projectId, t.id)}
                      aria-label={`Toggle ${t.name}`}
                    />
                    <Button
                      variant="link"
                      isDanger
                      size="sm"
                      onClick={() => {
                        deleteTool(projectId, t.id)
                        pushToast('Tool deleted', { kind: 'warning' })
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )
        ) : mcps.length === 0 ? (
          <EmptySplash
            title="No MCP servers"
            body="Connect an MCP server over HTTP/SSE or stdio. It will sync to OpenCode when the sandbox is running."
            primaryLabel="Create MCP server"
            onPrimary={() => setMcpOpen(true)}
          />
        ) : (
          mcps.map((m) => (
            <div className="list-card" key={m.id}>
              <div className="lc-row">
                <div>
                  <div className="lc-title">{m.name}</div>
                  <div className="lc-meta">
                    {m.transport} · {m.endpoint}
                    {m.status ? ` · ${m.status}` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Label color={m.on ? 'green' : 'grey'}>{m.on ? 'on' : 'off'}</Label>
                  {isApi && sandboxReady ? (
                    <Label color="blue" isCompact>
                      opencode
                    </Label>
                  ) : null}
                  <Switch
                    id={`mcp-${m.id}`}
                    isChecked={m.on}
                    onChange={() => void handleToggleMcp(m)}
                    aria-label={`Toggle ${m.name}`}
                    isDisabled={syncing}
                  />
                  <Button
                    variant="link"
                    isDanger
                    size="sm"
                    onClick={() => void handleDeleteMcp(m)}
                    isDisabled={syncing}
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
        isOpen={toolOpen}
        title="Create HTTP tool"
        onClose={() => setToolOpen(false)}
        onSubmit={() => {
          if (!toolName.trim()) return
          createTool(projectId, {
            name: toolName.trim(),
            method,
            url: url || `https://api.example.com/${toolName.trim()}`,
            on: true,
          })
          pushToast('Tool created', { kind: 'success' })
          setToolName('')
          setUrl('')
          setToolOpen(false)
        }}
        isSubmitDisabled={!toolName.trim()}
      >
        <FormGroup label="Name" isRequired fieldId="tool-name">
          <TextInput id="tool-name" value={toolName} onChange={(_e, v) => setToolName(v)} />
        </FormGroup>
        <FormGroup label="Method" fieldId="tool-method">
          <FormSelect id="tool-method" value={method} onChange={(_e, v) => setMethod(v)}>
            {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
              <FormSelectOption key={m} value={m} label={m} />
            ))}
          </FormSelect>
        </FormGroup>
        <FormGroup label="URL template" fieldId="tool-url">
          <TextInput id="tool-url" value={url} onChange={(_e, v) => setUrl(v)} placeholder="https://…" />
        </FormGroup>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={mcpOpen}
        title="Create MCP server"
        onClose={() => setMcpOpen(false)}
        onSubmit={() => void handleCreateMcp()}
        isSubmitDisabled={!mcpName.trim() || syncing}
        submitLabel={syncing ? 'Syncing…' : isApi ? 'Create & sync' : 'Create'}
      >
        <FormGroup label="Name" isRequired fieldId="mcp-name">
          <TextInput id="mcp-name" value={mcpName} onChange={(_e, v) => setMcpName(v)} />
        </FormGroup>
        <FormGroup label="Transport" fieldId="mcp-transport">
          <FormSelect id="mcp-transport" value={transport} onChange={(_e, v) => setTransport(v)}>
            <FormSelectOption value="HTTP/SSE" label="HTTP/SSE (remote URL)" />
            <FormSelectOption value="stdio" label="stdio (local command)" />
          </FormSelect>
        </FormGroup>
        <FormGroup
          label={transport.toLowerCase().includes('stdio') ? 'Command' : 'URL'}
          fieldId="mcp-ep"
        >
          <TextInput
            id="mcp-ep"
            value={endpoint}
            onChange={(_e, v) => setEndpoint(v)}
            placeholder={
              transport.toLowerCase().includes('stdio')
                ? 'npx -y @modelcontextprotocol/server-github'
                : 'https://…'
            }
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
