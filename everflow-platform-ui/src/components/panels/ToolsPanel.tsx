import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  Spinner,
  Switch,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import PlugIcon from '@patternfly/react-icons/dist/esm/icons/plug-icon'
import { Link } from 'react-router-dom'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { LOCAL_MARKETPLACE_CATALOG } from '@/data/marketplace'
import { getProject } from '@/data/projects'
import {
  getOpenCodeHarness,
  isSystemMcp,
  putOpenCodeHarness,
  slugifyAgentName,
} from '@/lib/harness/opencodePack'
import {
  createHttpTool,
  deleteHttpTool,
  getMarketplaceInstalled,
  isDemoMode,
  listHttpTools,
  testHttpTool,
  uninstallMarketplaceItem,
  updateHttpTool,
  type ApiHttpTool,
} from '@/lib/api'
import { ensureOpenCode, listMcp } from '@/lib/opencode/client'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { HttpToolDef, McpServerDef } from '@/types/studio'

type PluginRow = {
  id: string
  name: string
  source: string
  description?: string
  npmPackage?: string
}

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

function apiToolToDef(t: ApiHttpTool): HttpToolDef {
  return {
    id: t.id,
    name: t.name,
    method: t.method,
    url: t.url_template,
    on: t.enabled,
  }
}

export function ToolsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const isApi = Boolean(project?.fromApi) && !isDemoMode()
  const sandboxReady = !isApi || project?.sandboxStatus === 'running'

  const studio = useProjectStudio(projectId)
  const localHttpTools = studio.httpTools
  const localMcps = studio.mcps
  const createTool = useStudioDemoStore((s) => s.createTool)
  const deleteTool = useStudioDemoStore((s) => s.deleteTool)
  const createMcp = useStudioDemoStore((s) => s.createMcp)
  const deleteMcp = useStudioDemoStore((s) => s.deleteMcp)
  const toggleTool = useStudioDemoStore((s) => s.toggleTool)
  const toggleMcp = useStudioDemoStore((s) => s.toggleMcp)

  const [sub, setSub] = useState<'tools' | 'mcps' | 'plugins'>('tools')
  const [toolOpen, setToolOpen] = useState(false)
  const [mcpOpen, setMcpOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [liveMcp, setLiveMcp] = useState<McpServerDef[] | null>(null)
  const [plugins, setPlugins] = useState<PluginRow[]>([])
  const [pluginsLoading, setPluginsLoading] = useState(false)
  const [pluginBusyId, setPluginBusyId] = useState<string | null>(null)

  const [apiTools, setApiTools] = useState<HttpToolDef[]>([])
  const [toolsLoading, setToolsLoading] = useState(false)
  const [toolBusyId, setToolBusyId] = useState<string | null>(null)

  const [toolName, setToolName] = useState('')
  const [method, setMethod] = useState('GET')
  const [url, setUrl] = useState('')

  const [mcpName, setMcpName] = useState('')
  const [transport, setTransport] = useState('HTTP/SSE')
  const [endpoint, setEndpoint] = useState('')

  const httpTools = isApi ? apiTools : localHttpTools

  const refreshHttpTools = useCallback(async () => {
    if (!isApi || !projectId) {
      setApiTools([])
      return
    }
    try {
      const rows = await listHttpTools(projectId)
      setApiTools(rows.map(apiToolToDef))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load HTTP tools', { kind: 'danger' })
    }
  }, [isApi, projectId])

  useEffect(() => {
    if (!isApi) return
    setToolsLoading(true)
    void refreshHttpTools().finally(() => setToolsLoading(false))
  }, [isApi, refreshHttpTools])

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

  const refreshPlugins = useCallback(async () => {
    if (!isApi || !sandboxReady) {
      setPlugins([])
      return
    }
    setPluginsLoading(true)
    try {
      const [installed, harness] = await Promise.all([
        getMarketplaceInstalled(projectId).catch(() => null),
        getOpenCodeHarness(projectId).catch(() => null),
      ])
      const catalogPlugins = LOCAL_MARKETPLACE_CATALOG.plugins
      const byId = new Map(catalogPlugins.map((p) => [p.id, p]))
      const rows: PluginRow[] = []
      const seen = new Set<string>()

      for (const item of installed?.items || []) {
        if (item.kind !== 'plugin') continue
        const cat = byId.get(item.id)
        rows.push({
          id: item.id,
          name: cat?.name || item.name || item.id,
          source: item.source || cat?.source || 'marketplace',
          description: cat?.description,
          npmPackage: cat?.install?.plugin?.[0],
        })
        seen.add(item.id)
      }
      for (const pkg of harness?.plugins || installed?.plugins || []) {
        const name = String(pkg)
        if (seen.has(name)) continue
        const cat = byId.get(name)
        rows.push({
          id: name,
          name: cat?.name || name,
          source: 'opencode.json',
          description: cat?.description,
          npmPackage: name,
        })
        seen.add(name)
      }
      setPlugins(rows)
    } catch {
      setPlugins([])
    } finally {
      setPluginsLoading(false)
    }
  }, [isApi, sandboxReady, projectId])

  useEffect(() => {
    void refreshLiveMcp()
  }, [refreshLiveMcp])

  useEffect(() => {
    void refreshPlugins()
  }, [refreshPlugins])

  useEffect(() => {
    const onHarness = (ev: Event) => {
      const detail = (ev as CustomEvent<{ projectId?: string }>).detail
      if (detail?.projectId && detail.projectId !== projectId) return
      void refreshLiveMcp()
      void refreshPlugins()
    }
    window.addEventListener('everflow:harness-updated', onHarness)
    return () => window.removeEventListener('everflow:harness-updated', onHarness)
  }, [projectId, refreshLiveMcp, refreshPlugins])

  const mcps = liveMcp && liveMcp.length > 0 ? liveMcp : localMcps
  const systemMcps = mcps.filter((m) => isSystemMcp(m.name) || isSystemMcp(m.id))
  const userMcps = mcps.filter((m) => !isSystemMcp(m.name) && !isSystemMcp(m.id))
  const empty =
    sub !== 'plugins' && httpTools.length === 0 && mcps.length === 0 && !toolsLoading

  const handleRemovePlugin = async (plugin: PluginRow) => {
    if (!isApi || !sandboxReady) {
      pushToast('Start the sandbox to manage plugins', { kind: 'warning' })
      return
    }
    setPluginBusyId(plugin.id)
    try {
      const inCatalog = LOCAL_MARKETPLACE_CATALOG.plugins.some((p) => p.id === plugin.id)
      if (inCatalog) {
        await uninstallMarketplaceItem(projectId, 'plugin', plugin.id)
      } else {
        await putOpenCodeHarness(projectId, {
          remove_plugins: [plugin.npmPackage || plugin.id],
          remove_marketplace_items: [{ kind: 'plugin', id: plugin.id }],
        })
      }
      try {
        await ensureOpenCode(projectId, true)
      } catch {
        /* optional */
      }
      await refreshPlugins()
      window.dispatchEvent(new CustomEvent('everflow:harness-updated', { detail: { projectId } }))
      pushToast(`Removed plugin “${plugin.name}”`, { kind: 'warning' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to remove plugin', { kind: 'danger' })
    } finally {
      setPluginBusyId(null)
    }
  }

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
    if (isSystemMcp(m.name) || isSystemMcp(m.id)) {
      pushToast('Everflow MCP is a system server and cannot be deleted. Disable it per prompt in chat.', {
        kind: 'warning',
      })
      return
    }
    deleteMcp(projectId, m.id)
    if (isApi && sandboxReady) {
      setSyncing(true)
      try {
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

  const handleCreateTool = async () => {
    if (!toolName.trim()) return
    const name = toolName.trim()
    const urlTemplate = url || `https://api.example.com/${name}`
    if (isApi) {
      setSyncing(true)
      try {
        await createHttpTool(projectId, {
          name,
          method,
          url_template: urlTemplate,
          enabled: true,
        })
        await refreshHttpTools()
        pushToast(`HTTP tool “${name}” created`, { kind: 'success' })
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Failed to create HTTP tool', { kind: 'danger' })
        return
      } finally {
        setSyncing(false)
      }
    } else {
      createTool(projectId, {
        name,
        method,
        url: urlTemplate,
        on: true,
      })
      pushToast('Tool created', { kind: 'success' })
    }
    setToolName('')
    setUrl('')
    setToolOpen(false)
  }

  const handleToggleTool = async (t: HttpToolDef) => {
    if (!isApi) {
      toggleTool(projectId, t.id)
      return
    }
    setToolBusyId(t.id)
    try {
      await updateHttpTool(projectId, t.id, { enabled: !t.on })
      await refreshHttpTools()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to update tool', { kind: 'danger' })
    } finally {
      setToolBusyId(null)
    }
  }

  const handleDeleteTool = async (t: HttpToolDef) => {
    if (!isApi) {
      deleteTool(projectId, t.id)
      pushToast('Tool deleted', { kind: 'warning' })
      return
    }
    setToolBusyId(t.id)
    try {
      await deleteHttpTool(projectId, t.id)
      await refreshHttpTools()
      pushToast('Tool deleted', { kind: 'warning' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to delete tool', { kind: 'danger' })
    } finally {
      setToolBusyId(null)
    }
  }

  const handleTestTool = async (t: HttpToolDef) => {
    if (!isApi) {
      pushToast('Test runs against the platform API (open an API project).', { kind: 'warning' })
      return
    }
    setToolBusyId(t.id)
    try {
      const result = await testHttpTool(projectId, t.id)
      if (result.ok) {
        pushToast(
          `Test OK · HTTP ${result.status_code ?? '?'} · ${result.elapsed_ms}ms`,
          { kind: 'success' },
        )
      } else {
        pushToast(
          result.error || `Test failed · HTTP ${result.status_code ?? '?'}`,
          { kind: 'danger' },
        )
      }
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Test failed', { kind: 'danger' })
    } finally {
      setToolBusyId(null)
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
          <Tab
            eventKey="tools"
            title={
              <TabTitleText>
                HTTP tools ({httpTools.length})
                {isApi ? ' · API' : ''}
              </TabTitleText>
            }
          />
          <Tab
            eventKey="mcps"
            title={<TabTitleText>MCP servers ({userMcps.length})</TabTitleText>}
          />
          <Tab
            eventKey="plugins"
            title={<TabTitleText>Plugins ({plugins.length})</TabTitleText>}
          />
        </Tabs>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {sub === 'tools' && isApi ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setToolsLoading(true)
                void refreshHttpTools().finally(() => setToolsLoading(false))
              }}
              isDisabled={syncing || toolsLoading}
            >
              {toolsLoading ? 'Loading…' : 'Refresh'}
            </Button>
          ) : null}
          {sub === 'mcps' && isApi ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refreshLiveMcp()}
              isDisabled={syncing || !sandboxReady}
            >
              {syncing ? 'Syncing…' : 'Refresh status'}
            </Button>
          ) : null}
          {sub === 'plugins' && isApi ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refreshPlugins()}
              isDisabled={pluginsLoading || !sandboxReady}
            >
              {pluginsLoading ? 'Loading…' : 'Refresh'}
            </Button>
          ) : null}
          {sub === 'plugins' ? (
            <Link className="pf-v6-c-button pf-m-primary pf-m-small" to="/marketplace?tab=plugins">
              Browse Marketplace
            </Link>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={() => (sub === 'tools' ? setToolOpen(true) : setMcpOpen(true))}
              isDisabled={syncing}
            >
              {sub === 'tools' ? 'Create tool' : 'Create MCP'}
            </Button>
          )}
        </div>
      </div>
      <div className="panel-scroll">
        {sub === 'tools' && isApi ? (
          <p className="lc-meta" style={{ marginTop: 0 }}>
            HTTP tools are stored on the project and callable via Everflow MCP (
            <code>everflow_list_http_tools</code> / <code>everflow_call_http_tool</code>
            ). Outbound requests are SSRF-guarded.
          </p>
        ) : null}
        {sub === 'mcps' && isApi ? (
          <p className="lc-meta" style={{ marginTop: 0 }}>
            {!sandboxReady
              ? 'Sandbox not running — showing local catalog. Start the sandbox to sync MCP into OpenCode.'
              : liveMcp
                ? syncing
                  ? 'Syncing harness pack to OpenCode…'
                  : 'Synced from the OpenCode harness (opencode.json). Toggle updates the pack; assign per-agent in Agents. System servers (Everflow) cannot be deleted — deny them per prompt in the chat composer.'
                : 'Could not load live MCP status — showing local catalog. Use Refresh status when the sandbox is healthy.'}
          </p>
        ) : null}
        {sub === 'plugins' ? (
          <p className="lc-meta" style={{ marginTop: 0 }}>
            {!isApi
              ? 'Open an API project to manage OpenCode plugins installed from the Marketplace.'
              : !sandboxReady
                ? 'Start the sandbox to list and remove OpenCode plugins (opencode.json plugin array + marketplace skills/MCP).'
                : 'Plugins installed from Marketplace (Graphify, Oh My OpenCode, Headroom, …). Remove uninstalls the harness recipe.'}
          </p>
        ) : null}
        {sub === 'plugins' ? (
          !isApi || !sandboxReady ? (
            <EmptySplash
              title="Plugins unavailable"
              body={
                !isApi
                  ? 'Plugins are managed on API projects with a running OpenCode sandbox.'
                  : 'Start the project sandbox, then refresh to see installed plugins.'
              }
              primaryLabel="Browse Marketplace"
              onPrimary={() => {
                window.location.href = '/marketplace?tab=plugins'
              }}
              icon={PlugIcon}
            />
          ) : pluginsLoading && plugins.length === 0 ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
              <Spinner size="lg" aria-label="Loading plugins" />
            </div>
          ) : plugins.length === 0 ? (
            <EmptySplash
              title="No plugins installed"
              body="Add Graphify, Oh My OpenCode, Headroom, and more from the Marketplace."
              primaryLabel="Browse Marketplace"
              onPrimary={() => {
                window.location.href = '/marketplace?tab=plugins'
              }}
              icon={PlugIcon}
            />
          ) : (
            plugins.map((p) => (
              <div className="list-card" key={p.id}>
                <div className="lc-row">
                  <div>
                    <div className="lc-title">{p.name}</div>
                    <div className="lc-meta">
                      {p.description || p.source}
                      {p.npmPackage ? ` · ${p.npmPackage}` : ''}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Label color="blue" isCompact>
                      plugin
                    </Label>
                    <Button
                      variant="link"
                      isDanger
                      size="sm"
                      onClick={() => void handleRemovePlugin(p)}
                      isDisabled={pluginBusyId === p.id || syncing}
                    >
                      {pluginBusyId === p.id ? 'Removing…' : 'Remove'}
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )
        ) : sub === 'tools' && isApi && toolsLoading && httpTools.length === 0 ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}>
            <Spinner size="lg" aria-label="Loading HTTP tools" />
          </div>
        ) : empty ? (
          <EmptySplash
            title="No tools or MCP servers"
            body={
              isApi
                ? 'Register HTTP tools (persisted + MCP-callable) or MCP servers for OpenCode.'
                : 'Register HTTP tools and MCP servers so agents and chat can call them.'
            }
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
              body={
                isApi
                  ? 'Create an HTTP tool to expose a named method + URL template to agents via Everflow MCP.'
                  : 'Create a tool to expose an HTTP action to agents.'
              }
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
                    {isApi ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void handleTestTool(t)}
                        isDisabled={toolBusyId === t.id || syncing}
                      >
                        {toolBusyId === t.id ? 'Testing…' : 'Test'}
                      </Button>
                    ) : null}
                    <Switch
                      id={`tool-${t.id}`}
                      isChecked={t.on}
                      onChange={() => void handleToggleTool(t)}
                      aria-label={`Toggle ${t.name}`}
                      isDisabled={toolBusyId === t.id}
                    />
                    <Button
                      variant="link"
                      isDanger
                      size="sm"
                      onClick={() => void handleDeleteTool(t)}
                      isDisabled={toolBusyId === t.id}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )
        ) : (
          <>
            {systemMcps.length > 0 ? (
              <>
                <div className="section-label">System</div>
                {systemMcps.map((m) => {
                  const status = (m.status || '').toLowerCase()
                  const statusColor =
                    status.includes('connect') || status === 'ready' || status === 'ok'
                      ? 'green'
                      : status.includes('fail') ||
                          status.includes('error') ||
                          status === 'disconnected'
                        ? 'red'
                        : status
                          ? 'grey'
                          : null
                  return (
                    <div className="list-card" key={m.id}>
                      <div className="lc-row">
                        <div>
                          <div className="lc-title">{m.name}</div>
                          <div className="lc-meta">
                            Managed by Everflow — deny per prompt in chat
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Label color="grey" isCompact>
                            system
                          </Label>
                          {statusColor && m.status ? (
                            <Label color={statusColor} isCompact>
                              {m.status}
                            </Label>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </>
            ) : null}
            <div
              className="section-label"
              style={systemMcps.length > 0 ? { marginTop: 12 } : undefined}
            >
              MCP servers
            </div>
            {userMcps.length === 0 ? (
              <EmptySplash
                title="No MCP servers"
                body="Connect an MCP server over HTTP/SSE or stdio. It will sync to OpenCode when the sandbox is running."
                primaryLabel="Create MCP server"
                onPrimary={() => setMcpOpen(true)}
              />
            ) : (
              userMcps.map((m) => {
                const status = (m.status || '').toLowerCase()
                const statusColor =
                  status.includes('connect') || status === 'ready' || status === 'ok'
                    ? 'green'
                    : status.includes('fail') ||
                        status.includes('error') ||
                        status === 'disconnected'
                      ? 'red'
                      : status
                        ? 'grey'
                        : null
                return (
                  <div className="list-card" key={m.id}>
                    <div className="lc-row">
                      <div>
                        <div className="lc-title">{m.name}</div>
                        <div className="lc-meta">
                          {[m.transport, m.endpoint ? m.endpoint : null]
                            .filter(Boolean)
                            .join(' · ')}
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Label color={m.on ? 'green' : 'grey'}>
                          {m.on ? 'enabled' : 'disabled'}
                        </Label>
                        {statusColor && m.status ? (
                          <Label color={statusColor} isCompact>
                            {m.status}
                          </Label>
                        ) : null}
                        {isApi && sandboxReady && liveMcp?.some((x) => x.id === m.id) ? (
                          <Label color="blue" isCompact>
                            harness
                          </Label>
                        ) : isApi && !sandboxReady ? (
                          <Label color="grey" isCompact>
                            local
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
                )
              })
            )}
          </>
        )}
      </div>

      <CreateResourceModal
        isOpen={toolOpen}
        title="Create HTTP tool"
        onClose={() => setToolOpen(false)}
        onSubmit={() => void handleCreateTool()}
        isSubmitDisabled={!toolName.trim() || syncing}
        submitLabel={syncing ? 'Creating…' : 'Create'}
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
