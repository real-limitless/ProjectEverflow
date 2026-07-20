import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  FormGroup,
  Tabs,
  Tab,
  TabTitleText,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Node,
  type NodeProps,
  type Edge,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import { StatusLabel } from './statusLabel'
import type { WfNodeData, WfNodeKind } from '@/types/studio'

type FlowNode = Node<WfNodeData, 'studio'>

const PALETTE: { kind: WfNodeKind; label: string }[] = [
  { kind: 'trigger', label: 'Trigger' },
  { kind: 'http', label: 'HTTP' },
  { kind: 'llm', label: 'LLM' },
  { kind: 'code', label: 'Code' },
  { kind: 'condition', label: 'Condition' },
  { kind: 'notify', label: 'Notify' },
]

function StudioNode({ data }: NodeProps<FlowNode>) {
  return (
    <div className={`wf-node-card kind-${data.kind} ${data.running ? 'is-running' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <div style={{ fontSize: 9, opacity: 0.7, textTransform: 'uppercase' }}>{data.kind}</div>
      <div>{data.label}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { studio: StudioNode }

function toFlowNodes(raw: { id: string; position: { x: number; y: number }; data: WfNodeData }[]): FlowNode[] {
  return raw.map((n) => ({
    id: n.id,
    type: 'studio' as const,
    position: n.position,
    data: { ...n.data },
  }))
}

export function WorkflowsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const studio = useProjectStudio(projectId)
  const workflows = studio.workflows
  const workflowRuns = studio.workflowRuns
  const setWorkflowGraph = useStudioDemoStore((s) => s.setWorkflowGraph)
  const addWorkflowRun = useStudioDemoStore((s) => s.addWorkflowRun)
  const importN8n = useStudioDemoStore((s) => s.importN8n)

  const [sub, setSub] = useState<'canvas' | 'runs' | 'triggers'>('canvas')
  const [wfId, setWfId] = useState(workflows[0]?.id ?? '')
  const wf = workflows.find((w) => w.id === wfId) ?? workflows[0]

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(toFlowNodes(wf?.nodes ?? []))
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    (wf?.edges ?? []).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      markerEnd: { type: MarkerType.ArrowClosed },
    })),
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [running, setRunning] = useState(false)
  const persistTimer = useRef<number | null>(null)
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  nodesRef.current = nodes
  edgesRef.current = edges

  useEffect(() => {
    if (!wf) return
    setNodes(toFlowNodes(wf.nodes))
    setEdges(
      wf.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    )
    // Only re-hydrate when switching workflows; graph edits persist via setWorkflowGraph.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: wf.id only
  }, [wf?.id, setNodes, setEdges])

  const persist = useCallback(
    (n: FlowNode[], e: Edge[]) => {
      if (!wf) return
      if (persistTimer.current) window.clearTimeout(persistTimer.current)
      persistTimer.current = window.setTimeout(() => {
        setWorkflowGraph(
          projectId,
          wf.id,
          n.map((node) => ({
            id: node.id,
            type: 'studio',
            position: node.position,
            data: node.data,
          })),
          e.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
        )
      }, 300)
    },
    [projectId, setWorkflowGraph, wf],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => {
        const next = addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, eds)
        persist(nodesRef.current, next)
        return next
      })
    },
    [persist, setEdges],
  )

  const addNode = (kind: WfNodeKind) => {
    const id = `n-${Date.now()}`
    const node: FlowNode = {
      id,
      type: 'studio',
      position: { x: 120 + Math.random() * 200, y: 80 + Math.random() * 160 },
      data: { label: kind, kind, params: {} },
    }
    setNodes((ns) => {
      const next = [...ns, node]
      persist(next, edgesRef.current)
      return next
    })
  }

  const selected = nodes.find((n) => n.id === selectedId)

  const updateSelectedLabel = (label: string) => {
    setNodes((ns) => {
      const next = ns.map((n) =>
        n.id === selectedId ? { ...n, data: { ...n.data, label } } : n,
      )
      persist(next, edgesRef.current)
      return next
    })
  }

  const runWorkflow = async () => {
    if (!wf || running) return
    setRunning(true)
    const current = nodesRef.current
    const order = topological(current, edgesRef.current)
    const log: string[] = [`run ${wf.name}`]
    for (const id of order) {
      setNodes((ns) =>
        ns.map((n) => ({
          ...n,
          data: { ...n.data, running: n.id === id },
        })),
      )
      log.push(`execute ${current.find((n) => n.id === id)?.data.label ?? id}`)
      await new Promise((r) => setTimeout(r, 400))
    }
    setNodes((ns) => ns.map((n) => ({ ...n, data: { ...n.data, running: false } })))
    const ok = Math.random() > 0.15
    addWorkflowRun(projectId, {
      id: `r-${Date.now().toString(36)}`,
      workflowId: wf.id,
      status: ok ? 'ok' : 'err',
      dur: `${(order.length * 0.4).toFixed(1)}s`,
      when: 'just now',
      log,
    })
    setRunning(false)
    setSub('runs')
    pushToast(ok ? 'Workflow finished' : 'Workflow failed (demo)', {
      kind: ok ? 'success' : 'danger',
    })
  }

  const doImport = () => {
    try {
      const json = JSON.parse(importText) as unknown
      const id = importN8n(projectId, json)
      if (!id) throw new Error('import failed')
      setWfId(id)
      setImportOpen(false)
      setImportText('')
      pushToast('n8n workflow imported', { kind: 'success' })
    } catch {
      pushToast('Invalid n8n JSON', { kind: 'danger' })
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
          <Tab eventKey="canvas" title={<TabTitleText>Canvas</TabTitleText>} />
          <Tab eventKey="runs" title={<TabTitleText>Runs</TabTitleText>} />
          <Tab eventKey="triggers" title={<TabTitleText>Triggers</TabTitleText>} />
        </Tabs>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <select
            value={wf?.id ?? ''}
            onChange={(e) => setWfId(e.target.value)}
            style={{ fontSize: 12, maxWidth: 180 }}
            aria-label="Workflow"
          >
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <Button variant="secondary" size="sm" onClick={() => setImportOpen(true)}>
            Import n8n
          </Button>
          <Button variant="primary" size="sm" onClick={runWorkflow} isLoading={running} isDisabled={!wf || running}>
            Run
          </Button>
        </div>
      </div>

      {sub === 'canvas' && (
        <div className="wf-rf-root">
          <div className="wf-palette">
            <strong style={{ fontSize: 11 }}>Nodes</strong>
            {PALETTE.map((p) => (
              <Button key={p.kind} size="sm" variant="secondary" onClick={() => addNode(p.kind)}>
                + {p.label}
              </Button>
            ))}
          </div>
          {selected && (
            <div className="wf-inspector">
              <div className="section-label" style={{ marginTop: 0 }}>
                Inspector
              </div>
              <FormGroup label="Label" fieldId="wf-lab">
                <TextInput
                  id="wf-lab"
                  value={String(selected.data.label ?? '')}
                  onChange={(_e, v) => updateSelectedLabel(v)}
                />
              </FormGroup>
              <div className="lc-meta" style={{ marginTop: 6 }}>
                Kind: {String(selected.data.kind)}
              </div>
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={(ch) => {
              onNodesChange(ch)
              window.setTimeout(() => persist(nodesRef.current, edgesRef.current), 0)
            }}
            onEdgesChange={(ch) => {
              onEdgesChange(ch)
              window.setTimeout(() => persist(nodesRef.current, edgesRef.current), 0)
            }}
            onConnect={onConnect}
            onNodeClick={(_e, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
      )}

      {sub === 'runs' && (
        <div className="panel-scroll">
          {workflowRuns.map((r) => (
            <div className="list-card" key={r.id}>
              <div className="lc-row">
                <div className="lc-title" style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>
                  {r.id}
                </div>
                <StatusLabel status={r.status} />
              </div>
              <div className="lc-meta">
                {r.dur} · {r.when}
              </div>
              {r.log?.length > 0 && (
                <pre style={{ fontSize: 11, marginTop: 6, whiteSpace: 'pre-wrap' }}>
                  {r.log.join('\n')}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}

      {sub === 'triggers' && (
        <div className="panel-scroll">
          {workflows.map((w) => (
            <div className="list-card" key={w.id}>
              <div className="lc-title">{w.name}</div>
              <div className="lc-meta">
                Trigger: <code style={{ fontFamily: 'var(--mono)' }}>{w.trigger}</code> · {w.runs} runs
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateResourceModal
        isOpen={importOpen}
        title="Import n8n workflow JSON"
        onClose={() => setImportOpen(false)}
        onSubmit={doImport}
        submitLabel="Import"
      >
        <FormGroup label="Paste n8n export JSON" fieldId="n8n-json">
          <TextArea
            id="n8n-json"
            value={importText}
            onChange={(_e, v) => setImportText(v)}
            rows={10}
            resizeOrientation="vertical"
            placeholder='{"name":"My flow","nodes":[...],"connections":{...}}'
          />
        </FormGroup>
        <p className="lc-meta">
          Common node types map to Trigger / HTTP / LLM / Code / Condition / Notify; others become Unknown.
        </p>
      </CreateResourceModal>
    </div>
  )
}

function topological(nodes: FlowNode[], edges: Edge[]): string[] {
  const ids = nodes.map((n) => n.id)
  const indeg = new Map(ids.map((id) => [id, 0]))
  const adj = new Map(ids.map((id) => [id, [] as string[]]))
  edges.forEach((e) => {
    if (!indeg.has(e.target) || !adj.has(e.source)) return
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1)
    adj.get(e.source)!.push(e.target)
  })
  const q = ids.filter((id) => (indeg.get(id) ?? 0) === 0)
  const out: string[] = []
  while (q.length) {
    const id = q.shift()!
    out.push(id)
    for (const t of adj.get(id) ?? []) {
      indeg.set(t, (indeg.get(t) ?? 1) - 1)
      if ((indeg.get(t) ?? 0) === 0) q.push(t)
    }
  }
  ids.forEach((id) => {
    if (!out.includes(id)) out.push(id)
  })
  return out
}
