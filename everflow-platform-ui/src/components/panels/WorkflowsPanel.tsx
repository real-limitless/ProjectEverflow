import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  FormGroup,
  Switch,
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
  MarkerType,
  type Connection,
  type Node,
  type NodeProps,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { getProject } from '@/data/projects'
import { shortTypeLabel } from '@/lib/n8nImport'
import { pushToast } from '@/lib/studioToast'
import { graphToN8nDocument } from '@/lib/n8nExport'
import {
  cancelWorkflowRun,
  createDataTable,
  createWorkflow,
  createWorkflowCredential,
  deleteDataTable,
  deleteWorkflow,
  deleteWorkflowCredential,
  executeWorkflow,
  exportWorkflow,
  getDataTable,
  getWorkflow,
  getWorkflowRun,
  importWorkflow,
  listDataTables,
  listWorkflowCredentials,
  listWorkflowRuns,
  listWorkflows,
  updateWorkflow,
  validateWorkflowRun,
  type ApiDataTableRead,
  type ApiDataTableSummary,
  type ApiWorkflowCredential,
  type ApiWorkflowRead,
  type ApiWorkflowRun,
  type ApiWorkflowSummary,
} from '@/lib/workflowsApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import { StatusLabel } from './statusLabel'
import type { WfNodeData, WfNodeKind, WorkflowDef } from '@/types/studio'

type FlowNode = Node<WfNodeData, 'studio'>

const PALETTE: { kind: WfNodeKind; label: string; n8nType: string }[] = [
  { kind: 'trigger', label: 'Manual Trigger', n8nType: 'n8n-nodes-base.manualTrigger' },
  { kind: 'trigger', label: 'Schedule', n8nType: 'n8n-nodes-base.scheduleTrigger' },
  { kind: 'http', label: 'FTP', n8nType: 'n8n-nodes-base.ftp' },
  { kind: 'code', label: 'Code', n8nType: 'n8n-nodes-base.code' },
  { kind: 'transform', label: 'Set', n8nType: 'n8n-nodes-base.set' },
  { kind: 'transform', label: 'Split Out', n8nType: 'n8n-nodes-base.splitOut' },
  { kind: 'logic', label: 'Split In Batches', n8nType: 'n8n-nodes-base.splitInBatches' },
  { kind: 'condition', label: 'If', n8nType: 'n8n-nodes-base.if' },
  { kind: 'condition', label: 'Filter', n8nType: 'n8n-nodes-base.filter' },
  { kind: 'ai', label: 'AI Agent', n8nType: '@n8n/n8n-nodes-langchain.agent' },
  { kind: 'ai', label: 'OpenAI Chat Model', n8nType: '@n8n/n8n-nodes-langchain.lmChatOpenAi' },
  { kind: 'ai', label: 'MCP Client Tool', n8nType: '@n8n/n8n-nodes-langchain.mcpClientTool' },
  { kind: 'notify', label: 'Email', n8nType: 'n8n-nodes-base.emailSend' },
  { kind: 'http', label: 'Data Table', n8nType: 'n8n-nodes-base.dataTable' },
]

function connectionTypeFromHandles(connection: Connection): string {
  const th = connection.targetHandle || ''
  const sh = connection.sourceHandle || ''
  if (th.startsWith('ai_')) return th.split(':')[0] || th
  if (sh.startsWith('ai_')) return sh.split(':')[0] || 'main'
  return 'main'
}

function edgeVisuals(connectionType: string): Partial<Edge> {
  const isAi = connectionType !== 'main'
  return {
    className: isAi ? 'wf-edge-ai' : 'wf-edge-main',
    animated: isAi,
    style: isAi
      ? { stroke: 'var(--pf-t--global--color--purple--300, #a18fff)', strokeDasharray: '4 3' }
      : undefined,
    label: isAi ? connectionType.replace('ai_', '') : undefined,
    labelStyle: isAi ? { fontSize: 9, fill: '#888' } : undefined,
  }
}

const MULTI_OUTPUT: Record<string, { id: string; label: string }[]> = {
  'n8n-nodes-base.if': [
    { id: 'main:0:true', label: 'true' },
    { id: 'main:1:false', label: 'false' },
  ],
  'n8n-nodes-base.splitInBatches': [
    { id: 'main:0:done', label: 'done' },
    { id: 'main:1:loop', label: 'loop' },
  ],
}

function categoryClass(data: WfNodeData): string {
  const cat = data.category || data.kind
  return `kind-${cat}`
}

function StudioNode({ data }: NodeProps<FlowNode>) {
  const n8nType = data.n8nType || ''
  const multi = MULTI_OUTPUT[n8nType]
  const isAiSub =
    n8nType.includes('lmChat') ||
    n8nType.includes('mcpClientTool') ||
    n8nType.includes('languageModel')

  return (
    <div
      className={`wf-node-card ${categoryClass(data)} ${data.running || data.runStatus === 'running' ? 'is-running' : ''} ${
        data.runStatus === 'ok' ? 'is-run-ok' : ''
      } ${data.runStatus === 'err' ? 'is-run-err' : ''} ${
        data.supported === false ? 'is-unsupported' : ''
      } ${data.disabled ? 'is-disabled' : ''}`}
    >
      {!isAiSub && <Handle type="target" position={Position.Left} id="main" />}
      {isAiSub && (
        <Handle
          type="source"
          position={Position.Bottom}
          id={n8nType.includes('lmChat') ? 'ai_languageModel:0' : 'ai_tool:0'}
          className="wf-handle-ai"
        />
      )}
      <div className="wf-node-type">{shortTypeLabel(n8nType || String(data.kind))}</div>
      <div className="wf-node-label">{data.label}</div>
      {multi ? (
        multi.map((h, i) => (
          <Handle
            key={h.id}
            type="source"
            position={Position.Right}
            id={h.id}
            style={{ top: `${30 + i * 28}%` }}
            title={h.label}
          />
        ))
      ) : (
        !isAiSub && <Handle type="source" position={Position.Right} id="main:0" />
      )}
      {/* AI sub-node targets on agent */}
      {n8nType.includes('agent') && (
        <>
          <Handle
            type="target"
            position={Position.Top}
            id="ai_languageModel"
            className="wf-handle-ai"
            style={{ left: '35%' }}
            title="Language model"
          />
          <Handle
            type="target"
            position={Position.Top}
            id="ai_tool"
            className="wf-handle-ai"
            style={{ left: '65%' }}
            title="Tools"
          />
        </>
      )}
    </div>
  )
}

const nodeTypes = { studio: StudioNode }

function toFlowNodes(
  raw: { id: string; position: { x: number; y: number }; data: WfNodeData }[],
): FlowNode[] {
  return raw.map((n) => ({
    id: n.id,
    type: 'studio' as const,
    position: n.position,
    data: { ...n.data },
  }))
}

function toFlowEdges(
  raw: {
    id: string
    source: string
    target: string
    connectionType?: string
    sourceHandle?: string
  }[],
): Edge[] {
  return raw.map((e) => {
    const isAi = (e.connectionType || 'main') !== 'main'
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      targetHandle: isAi
        ? e.connectionType === 'ai_languageModel'
          ? 'ai_languageModel'
          : e.connectionType === 'ai_tool'
            ? 'ai_tool'
            : undefined
        : 'main',
      className: isAi ? 'wf-edge-ai' : 'wf-edge-main',
      animated: isAi,
      style: isAi
        ? { stroke: 'var(--pf-t--global--color--purple--300, #a18fff)', strokeDasharray: '4 3' }
        : undefined,
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { connectionType: e.connectionType || 'main' },
      label: isAi ? e.connectionType?.replace('ai_', '') : undefined,
      labelStyle: { fontSize: 9, fill: '#888' },
    }
  })
}

function apiToWorkflowDef(w: ApiWorkflowRead): WorkflowDef {
  return {
    id: w.id,
    name: w.name,
    status: w.active ? 'active' : 'idle',
    trigger: w.trigger_summary,
    runs: 0,
    active: w.active,
    fromApi: true,
    n8nDocument: w.n8n_document,
    importReport: w.import_report ?? w.graph.report,
    nodes: w.graph.nodes.map((n) => ({
      id: n.id,
      type: 'studio',
      position: n.position,
      data: {
        label: n.name,
        kind: (n.category || 'unknown') as WfNodeKind,
        n8nType: n.type,
        typeVersion: n.type_version,
        category: n.category,
        supported: n.supported,
        parameters: n.parameters,
        credentials: n.credentials,
        disabled: n.disabled,
        retryOnFail: n.retry_on_fail,
        maxTries: n.max_tries,
      },
    })),
    edges: w.graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      connectionType: e.connection_type,
      sourceHandle: e.source_handle,
      sourceIndex: e.source_index,
      targetIndex: e.target_index,
    })),
  }
}

export function WorkflowsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const project = getProject(projectId === 'default' ? null : projectId)
  const isApi = Boolean(project?.fromApi)

  const studio = useProjectStudio(projectId)
  const localWorkflows = studio.workflows
  const localRuns = studio.workflowRuns
  const setWorkflowGraph = useStudioDemoStore((s) => s.setWorkflowGraph)
  const addWorkflowRun = useStudioDemoStore((s) => s.addWorkflowRun)
  const importN8nLocal = useStudioDemoStore((s) => s.importN8n)
  const createBlankLocal = useStudioDemoStore((s) => s.createBlankWorkflow)
  const deleteLocalWorkflow = useStudioDemoStore((s) => s.deleteWorkflow)

  const [apiList, setApiList] = useState<ApiWorkflowSummary[]>([])
  const [apiWorkflows, setApiWorkflows] = useState<Record<string, WorkflowDef>>({})
  const [apiRuns, setApiRuns] = useState<ApiWorkflowRun[]>([])
  const [loading, setLoading] = useState(false)
  const [dataTables, setDataTables] = useState<ApiDataTableSummary[]>([])
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null)
  const [tableDetail, setTableDetail] = useState<ApiDataTableRead | null>(null)
  const [newTableOpen, setNewTableOpen] = useState(false)
  const [newTableName, setNewTableName] = useState('')
  const [newWfOpen, setNewWfOpen] = useState(false)
  const [newWfName, setNewWfName] = useState('Untitled workflow')

  const workflows = useMemo(() => {
    if (!isApi) return localWorkflows
    return apiList.map((s) => {
      const full = apiWorkflows[s.id]
      if (full) return full
      return {
        id: s.id,
        name: s.name,
        status: s.active ? 'active' : 'idle',
        trigger: s.trigger_summary,
        runs: 0,
        nodes: [],
        edges: [],
        active: s.active,
        fromApi: true,
      } satisfies WorkflowDef
    })
  }, [isApi, localWorkflows, apiList, apiWorkflows])

  const [sub, setSub] = useState<
    'library' | 'canvas' | 'runs' | 'triggers' | 'credentials' | 'tables'
  >('library')
  const [wfId, setWfId] = useState('')
  // Do not auto-select first workflow — library is the entry point
  const wf = workflows.find((w) => w.id === wfId)

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(toFlowNodes(wf?.nodes ?? []))
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(toFlowEdges(wf?.edges ?? []))
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importReport, setImportReport] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [triggerMode, setTriggerMode] = useState<'manual' | 'schedule' | 'executeWorkflow'>('manual')
  const [dryRun, setDryRun] = useState(true)
  const [credList, setCredList] = useState<ApiWorkflowCredential[]>([])
  const [credOpen, setCredOpen] = useState(false)
  const [bindOpen, setBindOpen] = useState(false)
  const [bindDraft, setBindDraft] = useState<Record<string, string>>({})
  const [credType, setCredType] = useState('smtp')
  const [credName, setCredName] = useState('')
  const [credPayloadJson, setCredPayloadJson] = useState('{}')
  const [savingActive, setSavingActive] = useState(false)
  const persistTimer = useRef<number | null>(null)
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  nodesRef.current = nodes
  edgesRef.current = edges

  const refreshApiList = useCallback(async () => {
    if (!isApi || !projectId) return
    setLoading(true)
    try {
      const list = await listWorkflows(projectId)
      setApiList(list)
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load workflows', { kind: 'danger' })
    } finally {
      setLoading(false)
    }
  }, [isApi, projectId])

  const refreshCreds = useCallback(async () => {
    if (!isApi || !projectId) return
    try {
      setCredList(await listWorkflowCredentials(projectId))
    } catch {
      setCredList([])
    }
  }, [isApi, projectId])

  useEffect(() => {
    void refreshApiList()
    void refreshCreds()
  }, [refreshApiList, refreshCreds])

  // Load full graph when selecting an API workflow
  useEffect(() => {
    if (!isApi || !wf?.id || !projectId) return
    if (apiWorkflows[wf.id]?.nodes.length) return
    let cancelled = false
    ;(async () => {
      try {
        const full = await getWorkflow(projectId, wf.id)
        if (cancelled) return
        setApiWorkflows((m) => ({ ...m, [full.id]: apiToWorkflowDef(full) }))
      } catch {
        /* empty list item until loaded */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isApi, wf?.id, projectId, apiWorkflows])

  useEffect(() => {
    if (!wf) return
    setNodes(toFlowNodes(wf.nodes))
    setEdges(toFlowEdges(wf.edges))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: wf.id only
  }, [wf?.id, wf?.nodes?.length, setNodes, setEdges])

  useEffect(() => {
    // Clear selection if deleted
    if (wfId && !workflows.some((w) => w.id === wfId)) {
      setWfId('')
      if (sub === 'canvas') setSub('library')
    }
  }, [workflows, wfId, sub])

  const refreshTables = useCallback(async () => {
    if (!isApi || !projectId) {
      setDataTables([])
      return
    }
    try {
      setDataTables(await listDataTables(projectId))
    } catch {
      setDataTables([])
    }
  }, [isApi, projectId])

  useEffect(() => {
    if (sub === 'tables') void refreshTables()
  }, [sub, refreshTables])

  useEffect(() => {
    if (!isApi || !selectedTableId || !projectId) {
      setTableDetail(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const d = await getDataTable(projectId, selectedTableId)
        if (!cancelled) setTableDetail(d)
      } catch {
        if (!cancelled) setTableDetail(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isApi, selectedTableId, projectId])

  const openWorkflow = async (id: string) => {
    setWfId(id)
    setSub('canvas')
    if (isApi && projectId && !apiWorkflows[id]?.nodes.length) {
      try {
        const full = await getWorkflow(projectId, id)
        setApiWorkflows((m) => ({ ...m, [full.id]: apiToWorkflowDef(full) }))
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Failed to open workflow', { kind: 'danger' })
      }
    }
  }

  const doCreateBlank = async () => {
    const name = newWfName.trim() || 'Untitled workflow'
    try {
      if (isApi) {
        const created = await createWorkflow(projectId, { name })
        setApiWorkflows((m) => ({ ...m, [created.id]: apiToWorkflowDef(created) }))
        await refreshApiList()
        setNewWfOpen(false)
        setNewWfName('Untitled workflow')
        await openWorkflow(created.id)
        pushToast(`Created “${name}”`, { kind: 'success' })
      } else {
        const id = createBlankLocal(projectId, name)
        setNewWfOpen(false)
        setNewWfName('Untitled workflow')
        setWfId(id)
        setSub('canvas')
        pushToast(`Created “${name}”`, { kind: 'success' })
      }
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Create failed', { kind: 'danger' })
    }
  }

  const doDeleteWorkflow = async (id: string, name: string) => {
    if (!window.confirm(`Delete workflow “${name}”? This cannot be undone.`)) return
    try {
      if (isApi) {
        await deleteWorkflow(projectId, id)
        setApiWorkflows((m) => {
          const next = { ...m }
          delete next[id]
          return next
        })
        await refreshApiList()
      } else {
        deleteLocalWorkflow(projectId, id)
      }
      if (wfId === id) {
        setWfId('')
        setSub('library')
      }
      pushToast('Workflow deleted', { kind: 'success' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Delete failed', { kind: 'danger' })
    }
  }

  useEffect(() => {
    if (!isApi || !wf?.id || sub !== 'runs') return
    let cancelled = false
    ;(async () => {
      try {
        const runs = await listWorkflowRuns(projectId, wf.id)
        if (!cancelled) setApiRuns(runs)
      } catch {
        if (!cancelled) setApiRuns([])
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isApi, wf?.id, projectId, sub])

  const persist = useCallback(
    (n: FlowNode[], e: Edge[]) => {
      if (!wf) return
      if (persistTimer.current) window.clearTimeout(persistTimer.current)
      persistTimer.current = window.setTimeout(() => {
        const mappedNodes = n.map((node) => ({
          id: node.id,
          type: 'studio' as const,
          position: node.position,
          data: node.data,
        }))
        const mappedEdges = e.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          connectionType: String(
            (edge.data as { connectionType?: string } | undefined)?.connectionType || 'main',
          ),
          sourceHandle: edge.sourceHandle ?? undefined,
          targetHandle: edge.targetHandle ?? undefined,
        }))
        if (!isApi) {
          setWorkflowGraph(projectId, wf.id, mappedNodes, mappedEdges)
          return
        }
        // API project: rebuild n8n document and PATCH
        const doc = graphToN8nDocument(wf.n8nDocument, n, mappedEdges as Parameters<typeof graphToN8nDocument>[2], {
          name: wf.name,
          active: wf.active,
        })
        void updateWorkflow(projectId, wf.id, { n8n_document: doc })
          .then((updated) => {
            setApiWorkflows((m) => ({ ...m, [updated.id]: apiToWorkflowDef(updated) }))
          })
          .catch((err) => {
            pushToast(err instanceof Error ? err.message : 'Failed to save graph', {
              kind: 'danger',
            })
          })
      }, 500)
    },
    [projectId, setWorkflowGraph, wf, isApi],
  )

  const applyRunLogToCanvas = useCallback(
    (log: unknown[] | null | undefined) => {
      if (!Array.isArray(log)) return
      const byName = new Map<string, 'ok' | 'err' | 'running'>()
      let current: string | null = null
      for (const x of log) {
        if (!x || typeof x !== 'object') continue
        const o = x as Record<string, unknown>
        if (o.summary) continue
        const name = String(o.node_name || '')
        if (!name) continue
        if (o.status === 'error') byName.set(name, 'err')
        else if (o.status === 'success') byName.set(name, 'ok')
        current = name
      }
      setNodes((ns) =>
        ns.map((n) => {
          const st = byName.get(String(n.data.label))
          const isCurrent = current === n.data.label && running
          return {
            ...n,
            data: {
              ...n.data,
              runStatus: isCurrent ? 'running' : st ?? null,
              running: isCurrent,
            },
          }
        }),
      )
    },
    [running, setNodes],
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      const connectionType = connectionTypeFromHandles(connection)
      setEdges((eds) => {
        const next = addEdge(
          {
            ...connection,
            markerEnd: { type: MarkerType.ArrowClosed },
            ...edgeVisuals(connectionType),
            data: { connectionType },
          },
          eds,
        )
        persist(nodesRef.current, next)
        return next
      })
    },
    [persist, setEdges],
  )

  const addNode = (kind: WfNodeKind, n8nType: string, label: string) => {
    const id = `n-${Date.now()}`
    const node: FlowNode = {
      id,
      type: 'studio',
      position: { x: 120 + Math.random() * 200, y: 80 + Math.random() * 160 },
      data: {
        label,
        kind,
        n8nType,
        category: kind,
        supported: true,
        parameters: {},
        params: {},
      },
    }
    setNodes((ns) => {
      const next = [...ns, node]
      persist(next, edgesRef.current)
      return next
    })
  }

  const doExport = async () => {
    if (!wf) return
    try {
      let doc: Record<string, unknown>
      if (isApi) {
        doc = await exportWorkflow(projectId, wf.id)
      } else {
        doc =
          wf.n8nDocument ||
          graphToN8nDocument(
            null,
            nodesRef.current,
            edgesRef.current.map((edge) => ({
              id: edge.id,
              source: edge.source,
              target: edge.target,
              connectionType: String(
                (edge.data as { connectionType?: string } | undefined)?.connectionType || 'main',
              ),
              sourceHandle: edge.sourceHandle ?? undefined,
              targetHandle: edge.targetHandle ?? undefined,
            })),
            {
              name: wf.name,
              active: wf.active,
            },
          )
      }
      const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(wf.name || 'workflow').replace(/\s+/g, '_')}.json`
      a.click()
      URL.revokeObjectURL(url)
      pushToast('Exported n8n JSON', { kind: 'success' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Export failed', { kind: 'danger' })
    }
  }

  const toggleActive = async (next: boolean) => {
    if (!wf || !isApi) return
    setSavingActive(true)
    try {
      const updated = await updateWorkflow(projectId, wf.id, { active: next })
      setApiWorkflows((m) => ({ ...m, [updated.id]: apiToWorkflowDef(updated) }))
      await refreshApiList()
      pushToast(next ? 'Workflow armed (active)' : 'Workflow disarmed', { kind: 'success' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to update active', { kind: 'danger' })
    } finally {
      setSavingActive(false)
    }
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

  const patchSelectedParameters = (patch: Record<string, unknown>) => {
    if (!selectedId) return
    setNodes((ns) => {
      const next = ns.map((n) => {
        if (n.id !== selectedId) return n
        const prev = (n.data.parameters || {}) as Record<string, unknown>
        return {
          ...n,
          data: {
            ...n.data,
            parameters: { ...prev, ...patch },
          },
        }
      })
      persist(next, edgesRef.current)
      return next
    })
  }

  const selectedN8n = String(selected?.data.n8nType || '')
  const selectedParams = (selected?.data.parameters || {}) as Record<string, unknown>
  const selectedOptions =
    selectedParams.options && typeof selectedParams.options === 'object'
      ? (selectedParams.options as Record<string, unknown>)
      : {}
  const selectedModelRaw = selectedParams.model
  const selectedModel =
    typeof selectedModelRaw === 'string'
      ? selectedModelRaw
      : selectedModelRaw && typeof selectedModelRaw === 'object'
        ? String(
            (selectedModelRaw as { value?: unknown; cachedResultName?: unknown }).value ??
              (selectedModelRaw as { cachedResultName?: unknown }).cachedResultName ??
              '',
          )
        : ''

  const pollRunUntilDone = async (runId: string) => {
    setActiveRunId(runId)
    for (let i = 0; i < 300; i++) {
      await new Promise((r) => setTimeout(r, 400))
      try {
        const r = await getWorkflowRun(projectId, wf!.id, runId)
        setApiRuns((prev) => {
          const rest = prev.filter((x) => x.id !== r.id)
          return [r, ...rest]
        })
        applyRunLogToCanvas(r.log)
        if (r.status !== 'running' && r.status !== 'pending') {
          setActiveRunId(null)
          return r
        }
      } catch {
        break
      }
    }
    setActiveRunId(null)
    return null
  }

  const runWorkflow = async () => {
    if (!wf || running) return
    setRunning(true)
    setNodes((ns) =>
      ns.map((n) => ({ ...n, data: { ...n.data, running: false, runStatus: null } })),
    )
    if (isApi) {
      try {
        if (!dryRun) {
          const v = await validateWorkflowRun(projectId, wf.id)
          if (v.missing_credentials.length) {
            const draft: Record<string, string> = {}
            for (const m of v.missing_credentials) {
              const key = m.n8n_name || m.credential_type
              draft[key] = ''
            }
            setBindDraft(draft)
            setBindOpen(true)
            pushToast(
              `Bind ${v.missing_credentials.length} credential(s) before live run`,
              { kind: 'warning' },
            )
            setRunning(false)
            return
          }
        }
        const run = await executeWorkflow(projectId, wf.id, {
          trigger: triggerMode,
          dry_run: dryRun,
          background: true,
          mocks: dryRun
            ? {
                capture_email: true,
                agent_output:
                  '# Dry-run research\n\n**Hold** core names. Connect live credentials for real data.\n',
              }
            : undefined,
        })
        setApiRuns((prev) => [run, ...prev])
        setSub('runs')
        const finished = await pollRunUntilDone(run.id)
        const final = finished || run
        if (final.status === 'success') {
          pushToast(dryRun ? 'Dry run finished' : 'Workflow finished', { kind: 'success' })
        } else if (final.status === 'cancelled') {
          pushToast('Run cancelled', { kind: 'info' })
        } else {
          pushToast(final.error_message || 'Workflow failed', { kind: 'danger' })
        }
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Execute failed', { kind: 'danger' })
      } finally {
        setRunning(false)
        setActiveRunId(null)
      }
      return
    }
    // Local demo: still use client topo walk when no API
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
      const node = current.find((n) => n.id === id)
      log.push(`execute ${node?.data.label ?? id} (${node?.data.n8nType || node?.data.kind})`)
      await new Promise((r) => setTimeout(r, 200))
    }
    setNodes((ns) => ns.map((n) => ({ ...n, data: { ...n.data, running: false } })))
    addWorkflowRun(projectId, {
      id: `r-${Date.now().toString(36)}`,
      workflowId: wf.id,
      status: 'ok',
      dur: `${(order.length * 0.2).toFixed(1)}s`,
      when: 'just now',
      log,
    })
    setRunning(false)
    setSub('runs')
    pushToast('Demo run finished (local preview — use API project for real engine)', {
      kind: 'success',
    })
  }

  const doImport = async () => {
    try {
      const json = JSON.parse(importText) as unknown
      if (isApi) {
        const created = await importWorkflow(projectId, json)
        const def = apiToWorkflowDef(created)
        setApiWorkflows((m) => ({ ...m, [def.id]: def }))
        await refreshApiList()
        setWfId(def.id)
        const rep = created.import_report || created.graph.report
        const nodeCount = (rep as { node_count?: number })?.node_count ?? def.nodes.length
        const unsup = (rep as { unsupported_types?: string[] })?.unsupported_types ?? []
        const credReqs =
          (rep as { credential_requirements?: { credential_type: string; n8n_name?: string | null }[] })
            ?.credential_requirements ?? []
        const creds = credReqs.length
        setImportReport(
          `Imported ${nodeCount} nodes · ${def.edges.length} edges · ${creds} credential type(s)${
            unsup.length ? ` · unsupported: ${unsup.join(', ')}` : ' · all types supported'
          }`,
        )
        pushToast(`Imported “${def.name}” (${nodeCount} nodes)`, { kind: 'success' })
        setSub('canvas')
        if (credReqs.length) {
          const draft: Record<string, string> = {}
          for (const c of credReqs) {
            draft[c.n8n_name || c.credential_type] = ''
          }
          setBindDraft(draft)
          setBindOpen(true)
          await refreshCreds()
        }
      } else {
        const id = importN8nLocal(projectId, json)
        if (!id) throw new Error('import failed')
        setWfId(id)
        setSub('canvas')
        const imported = useStudioDemoStore.getState().ensure(projectId).workflows.find((w) => w.id === id)
        const rep = imported?.importReport as
          | { nodeCount?: number; unsupportedTypes?: string[]; credentialRequirements?: unknown[] }
          | undefined
        setImportReport(
          `Imported ${rep?.nodeCount ?? imported?.nodes.length ?? '?'} nodes · ${
            imported?.edges.length ?? 0
          } edges · ${rep?.credentialRequirements?.length ?? 0} credential type(s)`,
        )
        pushToast('n8n workflow imported (local demo)', { kind: 'success' })
      }
      setImportOpen(false)
      setImportText('')
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Invalid n8n JSON', { kind: 'danger' })
    }
  }

  const onFile = (file: File | null) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setImportText(String(reader.result || ''))
    }
    reader.readAsText(file)
  }

  const displayRuns = isApi
    ? apiRuns.map((r) => {
        const stepLines: string[] = []
        if (Array.isArray(r.log)) {
          for (const x of r.log) {
            if (typeof x === 'string') {
              stepLines.push(x)
              continue
            }
            if (x && typeof x === 'object') {
              const o = x as Record<string, unknown>
              if (o.summary) {
                stepLines.push(
                  `── summary: ${String(o.status)} · emails=${
                    Array.isArray(o.sent_emails) ? o.sent_emails.length : 0
                  }`,
                )
                continue
              }
              if (o.node_name) {
                stepLines.push(
                  `${o.status === 'error' ? '✗' : '✓'} ${o.node_name}  in=${o.input_count ?? 0} out=${o.output_count ?? 0}${
                    o.error ? ` · ${o.error}` : ''
                  }`,
                )
              }
            }
          }
        }
        if (!stepLines.length && r.error_message) stepLines.push(r.error_message)
        return {
          id: r.id,
          status: r.status,
          dur: r.finished_at
            ? `${Math.max(
                0,
                (new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000,
              ).toFixed(1)}s`
            : '—',
          when: new Date(r.started_at).toLocaleString(),
          log: stepLines,
        }
      })
    : localRuns
        .filter((r) => !wf || r.workflowId === wf.id)
        .map((r) => ({
          id: r.id,
          status: r.status,
          dur: r.dur,
          when: r.when,
          log: r.log,
        }))

  const report = wf?.importReport as
    | {
        node_count?: number
        edge_count?: number
        nodeCount?: number
        edgeCount?: number
        unsupported_types?: string[]
        credential_requirements?: { credential_type: string; n8n_name?: string | null }[]
        credentialRequirements?: { credential_type: string; n8n_name?: string | null }[]
        connection_type_counts?: Record<string, number>
        connectionTypeCounts?: Record<string, number>
      }
    | undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="library" title={<TabTitleText>Library</TabTitleText>} />
          <Tab
            eventKey="canvas"
            title={<TabTitleText>Canvas</TabTitleText>}
            isDisabled={!wf}
          />
          <Tab eventKey="runs" title={<TabTitleText>Runs</TabTitleText>} isDisabled={!wf} />
          <Tab eventKey="triggers" title={<TabTitleText>Triggers</TabTitleText>} />
          {isApi && (
            <Tab eventKey="credentials" title={<TabTitleText>Credentials</TabTitleText>} />
          )}
          {isApi && <Tab eventKey="tables" title={<TabTitleText>Data tables</TabTitleText>} />}
        </Tabs>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {wf && sub !== 'library' && (
            <select
              value={wf.id}
              onChange={(e) => void openWorkflow(e.target.value)}
              style={{ fontSize: 12, maxWidth: 200 }}
              aria-label="Workflow"
            >
              {workflows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          )}
          <Button variant="secondary" size="sm" onClick={() => setNewWfOpen(true)}>
            New
          </Button>
          <select
            value={triggerMode}
            onChange={(e) => setTriggerMode(e.target.value as typeof triggerMode)}
            style={{ fontSize: 12 }}
            aria-label="Trigger"
            title="Entry trigger for Run"
          >
            <option value="manual">Manual</option>
            <option value="schedule">Schedule</option>
            <option value="executeWorkflow">Execute Workflow</option>
          </select>
          <label className="lc-meta" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Dry run
          </label>
          <Button variant="secondary" size="sm" onClick={() => setImportOpen(true)}>
            Import n8n
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void doExport()} isDisabled={!wf}>
            Export
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void runWorkflow()}
            isLoading={running}
            isDisabled={!wf || running}
          >
            Run
          </Button>
          {running && isApi && activeRunId && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                void cancelWorkflowRun(projectId, wf!.id, activeRunId).then(() =>
                  pushToast('Cancel requested', { kind: 'info' }),
                )
              }}
            >
              Cancel
            </Button>
          )}
          {loading && <span className="lc-meta">Loading…</span>}
        </div>
      </div>

      {importReport && (
        <div className="wf-import-banner" role="status">
          {importReport}
        </div>
      )}

      {sub === 'library' && (
        <div className="panel-scroll wf-library">
          <div className="wf-library-toolbar">
            <Button size="sm" variant="primary" onClick={() => setNewWfOpen(true)}>
              + New workflow
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setImportOpen(true)}>
              Import n8n
            </Button>
            {isApi && (
              <Button size="sm" variant="secondary" onClick={() => void refreshApiList()}>
                Refresh
              </Button>
            )}
            <span className="lc-meta" style={{ marginInlineStart: 'auto' }}>
              {workflows.length} workflow{workflows.length === 1 ? '' : 's'}
            </span>
          </div>
          {workflows.length === 0 && (
            <div className="list-card" style={{ margin: 12 }}>
              <div className="lc-title">No workflows yet</div>
              <p className="lc-meta">
                Create a blank canvas or import an n8n export (e.g. Stock Agent Emailer).
              </p>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <Button size="sm" onClick={() => setNewWfOpen(true)}>
                  New workflow
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setImportOpen(true)}>
                  Import n8n
                </Button>
              </div>
            </div>
          )}
          {workflows.length > 0 && (
            <table className="wf-library-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Trigger</th>
                  <th>Active</th>
                  <th>Nodes</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {workflows.map((w) => {
                  const summary = apiList.find((s) => s.id === w.id)
                  const nodeCount =
                    w.nodes?.length ||
                    summary?.node_count ||
                    (w.importReport as { node_count?: number; nodeCount?: number } | undefined)
                      ?.node_count ||
                    (w.importReport as { nodeCount?: number } | undefined)?.nodeCount ||
                    '—'
                  return (
                    <tr key={w.id} className={w.id === wfId ? 'is-selected' : undefined}>
                      <td>
                        <button
                          type="button"
                          className="wf-library-link"
                          onClick={() => void openWorkflow(w.id)}
                        >
                          {w.name}
                        </button>
                      </td>
                      <td>
                        <code style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{w.trigger}</code>
                      </td>
                      <td>{w.active ? '●' : '○'}</td>
                      <td>{nodeCount}</td>
                      <td style={{ textAlign: 'end', whiteSpace: 'nowrap' }}>
                        <Button size="sm" variant="primary" onClick={() => void openWorkflow(w.id)}>
                          Open
                        </Button>{' '}
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => void doDeleteWorkflow(w.id, w.name)}
                        >
                          Delete
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {sub === 'canvas' && wf && (
        <div className="wf-rf-root">
          <div className="wf-palette">
            <strong style={{ fontSize: 11 }}>Nodes</strong>
            {PALETTE.map((p) => (
              <Button
                key={p.n8nType + p.label}
                size="sm"
                variant="secondary"
                onClick={() => addNode(p.kind, p.n8nType, p.label)}
              >
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
                <div>
                  Type:{' '}
                  <code style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>
                    {selected.data.n8nType || selected.data.kind}
                  </code>
                </div>
                {selected.data.typeVersion != null && (
                  <div>Version: {String(selected.data.typeVersion)}</div>
                )}
                <div>Category: {String(selected.data.category || selected.data.kind)}</div>
                <div>
                  Supported:{' '}
                  {selected.data.supported === false ? (
                    <span style={{ color: 'var(--pf-t--global--color--status--danger--default)' }}>
                      no
                    </span>
                  ) : (
                    'yes'
                  )}
                </div>
                {selected.data.retryOnFail && (
                  <div>Retry on fail (max {selected.data.maxTries ?? '?'})</div>
                )}
              </div>
              {selectedN8n.includes('agent') && (
                <>
                  <FormGroup label="Prompt" fieldId="wf-agent-prompt" style={{ marginTop: 8 }}>
                    <TextArea
                      id="wf-agent-prompt"
                      rows={4}
                      resizeOrientation="vertical"
                      value={String(selectedParams.text ?? '')}
                      onChange={(_e, v) => patchSelectedParameters({ text: v })}
                    />
                  </FormGroup>
                  <FormGroup label="System message" fieldId="wf-agent-sys" style={{ marginTop: 8 }}>
                    <TextArea
                      id="wf-agent-sys"
                      rows={3}
                      resizeOrientation="vertical"
                      value={String(selectedOptions.systemMessage ?? '')}
                      onChange={(_e, v) =>
                        patchSelectedParameters({
                          options: { ...selectedOptions, systemMessage: v },
                        })
                      }
                    />
                  </FormGroup>
                </>
              )}
              {selectedN8n.includes('lmChatOpenAi') && (
                <FormGroup label="Model" fieldId="wf-lm-model" style={{ marginTop: 8 }}>
                  <TextInput
                    id="wf-lm-model"
                    value={selectedModel}
                    onChange={(_e, v) => {
                      const prev = selectedParams.model
                      if (prev && typeof prev === 'object') {
                        patchSelectedParameters({
                          model: {
                            ...(prev as Record<string, unknown>),
                            value: v,
                            cachedResultName: v,
                          },
                        })
                      } else {
                        patchSelectedParameters({
                          model: { __rl: true, mode: 'list', value: v, cachedResultName: v },
                        })
                      }
                    }}
                  />
                </FormGroup>
              )}
              {(selectedN8n.includes('mcpClientTool') || selectedN8n.includes('mcpClient')) && (
                <FormGroup label="Endpoint URL" fieldId="wf-mcp-url" style={{ marginTop: 8 }}>
                  <TextInput
                    id="wf-mcp-url"
                    value={String(selectedParams.endpointUrl ?? '')}
                    onChange={(_e, v) => patchSelectedParameters({ endpointUrl: v })}
                  />
                </FormGroup>
              )}
              {selected.data.credentials && (
                <div className="lc-meta" style={{ marginTop: 8 }}>
                  <strong>Credentials</strong>
                  <pre style={{ fontSize: 10, whiteSpace: 'pre-wrap', margin: '4px 0 0' }}>
                    {JSON.stringify(selected.data.credentials, null, 2)}
                  </pre>
                </div>
              )}
              {selected.data.parameters && Object.keys(selected.data.parameters).length > 0 && (
                <div className="lc-meta" style={{ marginTop: 8 }}>
                  <strong>Parameters</strong>
                  <pre className="wf-params-pre">
                    {JSON.stringify(selected.data.parameters, null, 2)}
                  </pre>
                </div>
              )}
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

      {sub === 'canvas' && !wf && (
        <div className="panel-scroll" style={{ padding: 16 }}>
          <p className="lc-meta">Select a workflow from the Library tab to open the canvas.</p>
          <Button size="sm" onClick={() => setSub('library')}>
            Go to Library
          </Button>
        </div>
      )}

      {sub === 'runs' && (
        <div className="panel-scroll">
          {!wf && (
            <p className="lc-meta" style={{ padding: 12 }}>
              Open a workflow from the Library to see its runs.
            </p>
          )}
          {wf && displayRuns.length === 0 && (
            <p className="lc-meta" style={{ padding: 12 }}>
              No runs yet. Open the canvas and click Run.
            </p>
          )}
          {wf &&
            displayRuns.map((r) => (
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

      {sub === 'tables' && isApi && (
        <div className="wf-tables-split">
          <div className="wf-tables-list">
            <div className="wf-library-toolbar">
              <Button size="sm" variant="primary" onClick={() => setNewTableOpen(true)}>
                + New table
              </Button>
              <Button size="sm" variant="secondary" onClick={() => void refreshTables()}>
                Refresh
              </Button>
            </div>
            {dataTables.length === 0 && (
              <p className="lc-meta" style={{ padding: 12 }}>
                No data tables yet. Runs that use Data Table nodes will create them, or add one
                here.
              </p>
            )}
            {dataTables.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`list-card wf-table-card ${selectedTableId === t.id ? 'is-selected' : ''}`}
                onClick={() => setSelectedTableId(t.id)}
              >
                <div className="lc-title">{t.name}</div>
                <div className="lc-meta">
                  {t.row_count} row{t.row_count === 1 ? '' : 's'}
                </div>
              </button>
            ))}
          </div>
          <div className="wf-tables-detail panel-scroll">
            {!selectedTableId && (
              <p className="lc-meta" style={{ padding: 12 }}>
                Select a table to preview rows.
              </p>
            )}
            {tableDetail && (
              <>
                <div className="lc-row" style={{ padding: '8px 12px' }}>
                  <div className="lc-title">{tableDetail.name}</div>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      if (!window.confirm(`Delete table “${tableDetail.name}”?`)) return
                      void deleteDataTable(projectId, tableDetail.id)
                        .then(() => {
                          setSelectedTableId(null)
                          setTableDetail(null)
                          return refreshTables()
                        })
                        .then(() => pushToast('Table deleted', { kind: 'success' }))
                    }}
                  >
                    Delete
                  </Button>
                </div>
                <div className="lc-meta" style={{ padding: '0 12px 8px' }}>
                  {tableDetail.row_count} total rows
                  {tableDetail.columns && tableDetail.columns.length > 0
                    ? ` · columns: ${tableDetail.columns
                        .map((c) =>
                          typeof c === 'object' && c && 'id' in c
                            ? String((c as { id: string }).id)
                            : JSON.stringify(c),
                        )
                        .join(', ')}`
                    : ''}
                </div>
                {tableDetail.rows.length === 0 ? (
                  <p className="lc-meta" style={{ padding: 12 }}>
                    Empty table.
                  </p>
                ) : (
                  <div style={{ overflow: 'auto', padding: 8 }}>
                    <table className="wf-library-table">
                      <thead>
                        <tr>
                          {Object.keys(tableDetail.rows[0] || {}).map((k) => (
                            <th key={k}>{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tableDetail.rows.map((row, i) => (
                          <tr key={i}>
                            {Object.keys(tableDetail.rows[0] || {}).map((k) => (
                              <td key={k} style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {typeof row[k] === 'object'
                                  ? JSON.stringify(row[k])
                                  : String(row[k] ?? '')}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {sub === 'triggers' && (
        <div className="panel-scroll">
          {workflows.map((w) => (
            <div className="list-card" key={w.id}>
              <div className="lc-row">
                <div className="lc-title">{w.name}</div>
                <Switch
                  id={`active-${w.id}`}
                  isChecked={Boolean(w.active)}
                  isDisabled={!isApi || savingActive || w.id !== wf?.id}
                  label={w.active ? 'Active' : 'Inactive'}
                  aria-label="Active"
                  onChange={(_e, checked) => {
                    if (w.id === wf?.id) void toggleActive(checked)
                  }}
                />
              </div>
              <div className="lc-meta">
                Trigger: <code style={{ fontFamily: 'var(--mono)' }}>{w.trigger}</code>
                {w.runs != null && ` · ${w.runs} runs`}
                {w.active ? ' · scheduler will arm scheduleTrigger hours' : ''}
              </div>
              {w.importReport && (
                <div className="lc-meta" style={{ marginTop: 4 }}>
                  Nodes:{' '}
                  {(report && w.id === wf?.id
                    ? report.node_count ?? report.nodeCount
                    : (w.importReport as { node_count?: number; nodeCount?: number }).node_count ??
                      (w.importReport as { nodeCount?: number }).nodeCount) ??
                    w.nodes.length}
                </div>
              )}
            </div>
          ))}
          {wf && report && (
            <div className="list-card" style={{ marginTop: 8 }}>
              <div className="lc-title">Import report — {wf.name}</div>
              <pre className="wf-params-pre" style={{ maxHeight: 240 }}>
                {JSON.stringify(
                  {
                    nodes: report.node_count ?? report.nodeCount,
                    edges: report.edge_count ?? report.edgeCount,
                    connections:
                      report.connection_type_counts ?? report.connectionTypeCounts,
                    credentials: (
                      report.credential_requirements ??
                      report.credentialRequirements ??
                      []
                    ).map((c) => `${c.credential_type}${c.n8n_name ? ` (${c.n8n_name})` : ''}`),
                    unsupported: report.unsupported_types ?? [],
                  },
                  null,
                  2,
                )}
              </pre>
            </div>
          )}
        </div>
      )}

      {sub === 'credentials' && isApi && (
        <div className="panel-scroll">
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, padding: '0 4px' }}>
            <Button size="sm" variant="primary" onClick={() => setCredOpen(true)}>
              Add credential
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setBindOpen(true)} isDisabled={!wf}>
              Bind to workflow
            </Button>
            <Button size="sm" variant="secondary" onClick={() => void refreshCreds()}>
              Refresh
            </Button>
          </div>
          {credList.length === 0 && (
            <p className="lc-meta" style={{ padding: 12 }}>
              No workflow credentials yet. Add openAiApi, ftp, smtp, httpMultipleHeadersAuth, or
              mcpClientApi secrets used by imported n8n nodes.
            </p>
          )}
          {credList.map((c) => (
            <div className="list-card" key={c.id}>
              <div className="lc-row">
                <div className="lc-title">{c.name}</div>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => {
                    void deleteWorkflowCredential(projectId, c.id)
                      .then(() => refreshCreds())
                      .then(() => pushToast('Credential deleted', { kind: 'success' }))
                      .catch((e) =>
                        pushToast(e instanceof Error ? e.message : 'Delete failed', {
                          kind: 'danger',
                        }),
                      )
                  }}
                >
                  Delete
                </Button>
              </div>
              <div className="lc-meta">
                Type: <code style={{ fontFamily: 'var(--mono)' }}>{c.credential_type}</code>
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateResourceModal
        isOpen={newWfOpen}
        title="New workflow"
        onClose={() => setNewWfOpen(false)}
        onSubmit={() => void doCreateBlank()}
        submitLabel="Create"
      >
        <FormGroup label="Name" fieldId="new-wf-name">
          <TextInput
            id="new-wf-name"
            value={newWfName}
            onChange={(_e, v) => setNewWfName(v)}
            placeholder="Untitled workflow"
          />
        </FormGroup>
        <p className="lc-meta">Starts with a Manual Trigger node. Import n8n for full graphs.</p>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={newTableOpen}
        title="New data table"
        onClose={() => setNewTableOpen(false)}
        onSubmit={() => {
          void (async () => {
            try {
              const name = newTableName.trim()
              if (!name) throw new Error('Name required')
              const t = await createDataTable(projectId, { name })
              setNewTableOpen(false)
              setNewTableName('')
              await refreshTables()
              setSelectedTableId(t.id)
              pushToast(`Table “${name}” created`, { kind: 'success' })
            } catch (e) {
              pushToast(e instanceof Error ? e.message : 'Create table failed', {
                kind: 'danger',
              })
            }
          })()
        }}
        submitLabel="Create"
      >
        <FormGroup label="Table name" fieldId="new-table-name">
          <TextInput
            id="new-table-name"
            value={newTableName}
            onChange={(_e, v) => setNewTableName(v)}
            placeholder="temp_table"
          />
        </FormGroup>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={importOpen}
        title="Import n8n workflow JSON"
        onClose={() => setImportOpen(false)}
        onSubmit={() => void doImport()}
        submitLabel="Import"
      >
        <FormGroup label="Upload .json file" fieldId="n8n-file">
          <input
            id="n8n-file"
            type="file"
            accept="application/json,.json"
            onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            style={{ fontSize: 12 }}
          />
        </FormGroup>
        <FormGroup label="Or paste n8n export JSON" fieldId="n8n-json">
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
          Full n8n export is preserved. After import you can bind credentials and run (dry-run or
          live).
        </p>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={credOpen}
        title="Add workflow credential"
        onClose={() => setCredOpen(false)}
        onSubmit={() => {
          void (async () => {
            try {
              const payload = JSON.parse(credPayloadJson || '{}') as Record<string, unknown>
              await createWorkflowCredential(projectId, {
                credential_type: credType,
                name: credName || credType,
                payload,
              })
              await refreshCreds()
              setCredOpen(false)
              setCredName('')
              setCredPayloadJson('{}')
              pushToast('Credential saved', { kind: 'success' })
            } catch (e) {
              pushToast(e instanceof Error ? e.message : 'Invalid payload JSON', {
                kind: 'danger',
              })
            }
          })()
        }}
        submitLabel="Save"
      >
        <FormGroup label="Type" fieldId="cred-type">
          <select
            id="cred-type"
            value={credType}
            onChange={(e) => {
              setCredType(e.target.value)
              const samples: Record<string, string> = {
                smtp: '{"host":"smtp.example.com","port":587,"user":"","password":"","fromEmail":"robot@example.com"}',
                ftp: '{"host":"ftp.example.com","port":21,"user":"","password":""}',
                openAiApi:
                  '{"apiKey":"sk-...","baseUrl":"https://api.openai.com/v1"}',
                httpMultipleHeadersAuth:
                  '{"headers":{"X-RapidAPI-Key":"...","X-RapidAPI-Host":"..."}}',
                mcpClientApi: '{"command":["npx","-y","@modelcontextprotocol/server-..."]}',
              }
              setCredPayloadJson(samples[e.target.value] || '{}')
            }}
            style={{ width: '100%', fontSize: 12 }}
          >
            <option value="openAiApi">openAiApi</option>
            <option value="ftp">ftp</option>
            <option value="smtp">smtp</option>
            <option value="httpMultipleHeadersAuth">httpMultipleHeadersAuth</option>
            <option value="mcpClientApi">mcpClientApi</option>
          </select>
        </FormGroup>
        <FormGroup label="Name (match n8n credential name if possible)" fieldId="cred-name">
          <TextInput
            id="cred-name"
            value={credName}
            onChange={(_e, v) => setCredName(v)}
            placeholder="SMTP account"
          />
        </FormGroup>
        <FormGroup label="Payload JSON" fieldId="cred-payload">
          <TextArea
            id="cred-payload"
            value={credPayloadJson}
            onChange={(_e, v) => setCredPayloadJson(v)}
            rows={6}
            resizeOrientation="vertical"
          />
        </FormGroup>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={bindOpen}
        title="Bind n8n credentials → Everflow secrets"
        onClose={() => setBindOpen(false)}
        onSubmit={() => {
          void (async () => {
            if (!wf) return
            try {
              const bindings: Record<string, string> = {
                ...((wf as WorkflowDef & { credential_bindings?: Record<string, string> })
                  .n8nDocument && {}),
              }
              // Map each draft key (n8n name) → everflow credential id
              for (const [n8nName, everflowId] of Object.entries(bindDraft)) {
                if (everflowId) bindings[n8nName] = everflowId
              }
              const updated = await updateWorkflow(projectId, wf.id, {
                credential_bindings: bindings,
              })
              setApiWorkflows((m) => ({ ...m, [updated.id]: apiToWorkflowDef(updated) }))
              setBindOpen(false)
              pushToast('Credential bindings saved', { kind: 'success' })
            } catch (e) {
              pushToast(e instanceof Error ? e.message : 'Bind failed', { kind: 'danger' })
            }
          })()
        }}
        submitLabel="Save bindings"
      >
        <p className="lc-meta">
          Map each n8n credential name to a stored Everflow secret. Create secrets in the
          Credentials tab first.
        </p>
        {Object.keys(bindDraft).length === 0 && (
          <p className="lc-meta">No pending bindings — re-import or open after validate.</p>
        )}
        {Object.keys(bindDraft).map((n8nName) => (
          <FormGroup key={n8nName} label={n8nName} fieldId={`bind-${n8nName}`}>
            <select
              id={`bind-${n8nName}`}
              value={bindDraft[n8nName] || ''}
              onChange={(e) =>
                setBindDraft((d) => ({ ...d, [n8nName]: e.target.value }))
              }
              style={{ width: '100%', fontSize: 12 }}
            >
              <option value="">— select —</option>
              {credList.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.credential_type})
                </option>
              ))}
            </select>
          </FormGroup>
        ))}
      </CreateResourceModal>
    </div>
  )
}

function topological(nodes: FlowNode[], edges: Edge[]): string[] {
  const ids = nodes.map((n) => n.id)
  const indeg = new Map(ids.map((id) => [id, 0]))
  const adj = new Map(ids.map((id) => [id, [] as string[]]))
  edges.forEach((e) => {
    // AI edges are not execution predecessors on main chain
    const ctype = (e.data as { connectionType?: string } | undefined)?.connectionType || 'main'
    if (ctype !== 'main') return
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
