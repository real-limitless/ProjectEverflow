/**
 * Rebuild an n8n document from canvas graph edits while preserving
 * parameters / credentials from the previous document.
 */

export interface CanvasNodeLike {
  id: string
  position: { x: number; y: number }
  data: {
    label?: string
    n8nType?: string
    typeVersion?: number | null
    parameters?: Record<string, unknown>
    credentials?: Record<string, unknown> | null
    disabled?: boolean
    retryOnFail?: boolean
    maxTries?: number | null
  }
}

export interface CanvasEdgeLike {
  id: string
  source: string
  target: string
  connectionType?: string
  sourceHandle?: string
  targetHandle?: string
  sourceIndex?: number
  targetIndex?: number
  data?: { connectionType?: string }
}

function parseSourceIndex(handle?: string, fallback = 0): number {
  if (!handle) return fallback
  const m = handle.match(/:(\d+)/)
  return m ? Number(m[1]) : fallback
}

function parseConnectionType(
  sourceHandle?: string,
  edgeType?: string,
  targetHandle?: string,
): string {
  if (edgeType && edgeType !== 'main') return edgeType
  for (const handle of [targetHandle, sourceHandle]) {
    if (!handle) continue
    if (handle.startsWith('ai_')) return handle.split(':')[0] || 'main'
    if (handle.startsWith('main')) return 'main'
  }
  return edgeType || 'main'
}

export function graphToN8nDocument(
  existing: Record<string, unknown> | null | undefined,
  nodes: CanvasNodeLike[],
  edges: CanvasEdgeLike[],
  opts?: { name?: string; active?: boolean },
): Record<string, unknown> {
  const base = existing && typeof existing === 'object' ? { ...existing } : {}
  const prevNodes = Array.isArray(base.nodes) ? (base.nodes as Record<string, unknown>[]) : []
  const prevById = new Map(prevNodes.map((n) => [String(n.id), n]))
  const prevByName = new Map(prevNodes.map((n) => [String(n.name), n]))

  const outNodes = nodes.map((n, i) => {
    const prev =
      prevById.get(n.id) ||
      prevByName.get(String(n.data.label || '')) ||
      {}
    const name = String(n.data.label || prev.name || `Node ${i + 1}`)
    const type = String(n.data.n8nType || prev.type || 'n8n-nodes-base.noOp')
    return {
      ...prev,
      id: n.id,
      name,
      type,
      typeVersion: n.data.typeVersion ?? prev.typeVersion ?? 1,
      position: [n.position.x, n.position.y],
      parameters: n.data.parameters ?? prev.parameters ?? {},
      credentials: n.data.credentials ?? prev.credentials,
      disabled: n.data.disabled ?? prev.disabled,
      retryOnFail: n.data.retryOnFail ?? prev.retryOnFail,
      maxTries: n.data.maxTries ?? prev.maxTries,
    }
  })

  const idToName = new Map(outNodes.map((n) => [String(n.id), String(n.name)]))
  const connections: Record<string, Record<string, { node: string; type: string; index: number }[][]>> =
    {}

  for (const e of edges) {
    const sourceName = idToName.get(e.source)
    const targetName = idToName.get(e.target)
    if (!sourceName || !targetName) continue
    const ctype = parseConnectionType(
      e.sourceHandle,
      e.connectionType || e.data?.connectionType,
      e.targetHandle,
    )
    const sIdx = e.sourceIndex ?? parseSourceIndex(e.sourceHandle, 0)
    const tIdx = e.targetIndex ?? 0
    if (!connections[sourceName]) connections[sourceName] = {}
    if (!connections[sourceName][ctype]) connections[sourceName][ctype] = []
    const groups = connections[sourceName][ctype]
    while (groups.length <= sIdx) groups.push([])
    groups[sIdx]!.push({ node: targetName, type: ctype, index: tIdx })
  }

  return {
    ...base,
    name: opts?.name ?? base.name ?? 'Workflow',
    active: opts?.active ?? base.active ?? false,
    nodes: outNodes,
    connections,
  }
}
