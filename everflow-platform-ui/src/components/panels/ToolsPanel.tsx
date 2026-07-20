import { useState } from 'react'
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
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'

export function ToolsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const studio = useProjectStudio(projectId)
  const httpTools = studio.httpTools
  const mcps = studio.mcps
  const createTool = useStudioDemoStore((s) => s.createTool)
  const deleteTool = useStudioDemoStore((s) => s.deleteTool)
  const createMcp = useStudioDemoStore((s) => s.createMcp)
  const deleteMcp = useStudioDemoStore((s) => s.deleteMcp)
  const toggleTool = useStudioDemoStore((s) => s.toggleTool)
  const toggleMcp = useStudioDemoStore((s) => s.toggleMcp)

  const [sub, setSub] = useState<'tools' | 'mcps'>('tools')
  const [toolOpen, setToolOpen] = useState(false)
  const [mcpOpen, setMcpOpen] = useState(false)

  const [toolName, setToolName] = useState('')
  const [method, setMethod] = useState('GET')
  const [url, setUrl] = useState('')

  const [mcpName, setMcpName] = useState('')
  const [transport, setTransport] = useState('HTTP/SSE')
  const [endpoint, setEndpoint] = useState('')

  const empty = httpTools.length === 0 && mcps.length === 0

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
        >
          {sub === 'tools' ? 'Create tool' : 'Create MCP'}
        </Button>
      </div>
      <div className="panel-scroll">
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
            body="Connect an MCP server over HTTP/SSE or stdio (demo)."
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
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Label color={m.on ? 'green' : 'grey'}>{m.on ? 'on' : 'off'}</Label>
                  <Switch
                    id={`mcp-${m.id}`}
                    isChecked={m.on}
                    onChange={() => toggleMcp(projectId, m.id)}
                    aria-label={`Toggle ${m.name}`}
                  />
                  <Button
                    variant="link"
                    isDanger
                    size="sm"
                    onClick={() => {
                      deleteMcp(projectId, m.id)
                      pushToast('MCP deleted', { kind: 'warning' })
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
        onSubmit={() => {
          if (!mcpName.trim()) return
          createMcp(projectId, {
            name: mcpName.trim(),
            transport,
            endpoint: endpoint || 'https://mcp.example.com/sse',
            on: true,
          })
          pushToast('MCP server created', { kind: 'success' })
          setMcpName('')
          setEndpoint('')
          setMcpOpen(false)
        }}
        isSubmitDisabled={!mcpName.trim()}
      >
        <FormGroup label="Name" isRequired fieldId="mcp-name">
          <TextInput id="mcp-name" value={mcpName} onChange={(_e, v) => setMcpName(v)} />
        </FormGroup>
        <FormGroup label="Transport" fieldId="mcp-transport">
          <FormSelect id="mcp-transport" value={transport} onChange={(_e, v) => setTransport(v)}>
            <FormSelectOption value="HTTP/SSE" label="HTTP/SSE" />
            <FormSelectOption value="stdio" label="stdio" />
          </FormSelect>
        </FormGroup>
        <FormGroup label="Endpoint / command" fieldId="mcp-ep">
          <TextInput id="mcp-ep" value={endpoint} onChange={(_e, v) => setEndpoint(v)} />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
