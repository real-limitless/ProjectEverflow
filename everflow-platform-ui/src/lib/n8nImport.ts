/**
 * Client-side n8n export → canvas graph (mirrors API import_n8n.derive_graph).
 * Used for demo projects offline; API projects prefer server import.
 */

export type WfCategory =
  | 'trigger'
  | 'input'
  | 'transform'
  | 'logic'
  | 'ai'
  | 'output'
  | 'data'
  | 'unknown'

/** @deprecated Prefer WfCategory; kept for palette / legacy demo nodes */
export type WfNodeKind =
  | 'trigger'
  | 'http'
  | 'llm'
  | 'code'
  | 'condition'
  | 'notify'
  | 'unknown'
  | WfCategory

const SUPPORTED: Record<string, WfCategory> = {
  'n8n-nodes-base.manualTrigger': 'trigger',
  'n8n-nodes-base.scheduleTrigger': 'trigger',
  'n8n-nodes-base.executeWorkflowTrigger': 'trigger',
  'n8n-nodes-base.ftp': 'input',
  'n8n-nodes-base.extractFromFile': 'transform',
  'n8n-nodes-base.convertToFile': 'transform',
  'n8n-nodes-base.filter': 'logic',
  'n8n-nodes-base.set': 'transform',
  'n8n-nodes-base.code': 'transform',
  'n8n-nodes-base.aggregate': 'transform',
  'n8n-nodes-base.splitOut': 'transform',
  'n8n-nodes-base.splitInBatches': 'logic',
  'n8n-nodes-base.if': 'logic',
  'n8n-nodes-base.dataTable': 'data',
  'n8n-nodes-base.emailSend': 'output',
  '@n8n/n8n-nodes-langchain.lmChatOpenAi': 'ai',
  '@n8n/n8n-nodes-langchain.agent': 'ai',
  '@n8n/n8n-nodes-langchain.mcpClientTool': 'ai',
  'n8n-nodes-mcp.mcpClientTool': 'ai',
}

const MULTI_MAIN: Record<string, string[]> = {
  'n8n-nodes-base.if': ['true', 'false'],
  'n8n-nodes-base.splitInBatches': ['done', 'loop'],
}

export interface N8nGraphNode {
  id: string
  name: string
  type: string
  typeVersion?: number | null
  position: { x: number; y: number }
  parameters: Record<string, unknown>
  credentials?: Record<string, { id?: string; name?: string }> | null
  category: WfCategory
  supported: boolean
  disabled?: boolean
  retryOnFail?: boolean
  maxTries?: number | null
}

export interface N8nGraphEdge {
  id: string
  source: string
  target: string
  sourceName: string
  targetName: string
  connectionType: string
  sourceIndex: number
  targetIndex: number
  sourceHandle: string
}

export interface N8nImportReport {
  nodeCount: number
  edgeCount: number
  supportedTypes: string[]
  unsupportedTypes: string[]
  credentialRequirements: {
    credential_type: string
    n8n_id: string | null
    n8n_name: string | null
    used_by_nodes: string[]
  }[]
  triggerSummary: string
  connectionTypeCounts: Record<string, number>
  warnings: string[]
}

export interface N8nDerivedGraph {
  name: string
  active: boolean
  settings: Record<string, unknown>
  pinData: Record<string, unknown>
  nodes: N8nGraphNode[]
  edges: N8nGraphEdge[]
  report: N8nImportReport
}

function pos(raw: unknown, i: number): { x: number; y: number } {
  if (Array.isArray(raw) && raw.length >= 2) {
    return { x: Number(raw[0]) || 0, y: Number(raw[1]) || 0 }
  }
  if (raw && typeof raw === 'object') {
    const o = raw as { x?: number; y?: number }
    return { x: Number(o.x) || i * 160, y: Number(o.y) || 100 }
  }
  return { x: i * 160, y: 100 }
}

function triggerSummary(types: string[]): string {
  const flags = new Set<string>()
  for (const t of types) {
    if (t.includes('manualTrigger')) flags.add('manual')
    else if (t.includes('scheduleTrigger')) flags.add('schedule')
    else if (t.includes('executeWorkflowTrigger')) flags.add('executeWorkflow')
    else if (t.toLowerCase().includes('webhook')) flags.add('webhook')
    else if (t.toLowerCase().includes('trigger')) flags.add('other')
  }
  if (!flags.size) return 'unknown'
  if (flags.size === 1) return [...flags][0]!
  return 'mixed'
}

function sourceHandle(ctype: string, index: number, sourceType: string): string {
  if (ctype === 'main') {
    const labels = MULTI_MAIN[sourceType]
    if (labels && index < labels.length) return `main:${index}:${labels[index]}`
    return `main:${index}`
  }
  return `${ctype}:${index}`
}

export function categorizeN8nType(n8nType: string): WfCategory {
  return SUPPORTED[n8nType] ?? 'unknown'
}

export function shortTypeLabel(n8nType: string): string {
  const last = n8nType.split('.').pop() || n8nType
  return last.replace(/^lmChat/, '').replace(/Tool$/, '')
}

export function deriveN8nGraph(document: unknown): N8nDerivedGraph {
  if (!document || typeof document !== 'object') {
    throw new Error('n8n document must be a JSON object')
  }
  const doc = document as Record<string, unknown>
  const rawNodes = doc.nodes
  if (!Array.isArray(rawNodes)) throw new Error("n8n document missing 'nodes' array")

  const nodes: N8nGraphNode[] = []
  const nameToId = new Map<string, string>()
  const typeByName = new Map<string, string>()
  const supportedTypes = new Set<string>()
  const unsupportedTypes = new Set<string>()
  const credMap = new Map<
    string,
    N8nImportReport['credentialRequirements'][number]
  >()
  const warnings: string[] = []

  rawNodes.forEach((raw, i) => {
    if (!raw || typeof raw !== 'object') return
    const n = raw as Record<string, unknown>
    const nType = String(n.type || 'unknown')
    const nId = String(n.id || `node-${i}`)
    const nName = String(n.name || `Node ${i + 1}`)
    const supported = nType in SUPPORTED
    if (supported) supportedTypes.add(nType)
    else unsupportedTypes.add(nType)

    const creds =
      n.credentials && typeof n.credentials === 'object'
        ? (n.credentials as Record<string, { id?: string; name?: string }>)
        : null
    if (creds) {
      for (const [credType, meta] of Object.entries(creds)) {
        const key = `${credType}|${meta?.id ?? ''}|${meta?.name ?? ''}`
        const existing = credMap.get(key)
        if (existing) existing.used_by_nodes.push(nName)
        else {
          credMap.set(key, {
            credential_type: credType,
            n8n_id: meta?.id != null ? String(meta.id) : null,
            n8n_name: meta?.name != null ? String(meta.name) : null,
            used_by_nodes: [nName],
          })
        }
      }
    }

    const parameters =
      n.parameters && typeof n.parameters === 'object'
        ? (n.parameters as Record<string, unknown>)
        : {}

    nodes.push({
      id: nId,
      name: nName,
      type: nType,
      typeVersion: typeof n.typeVersion === 'number' ? n.typeVersion : null,
      position: pos(n.position, i),
      parameters,
      credentials: creds,
      category: categorizeN8nType(nType),
      supported,
      disabled: Boolean(n.disabled),
      retryOnFail: Boolean(n.retryOnFail),
      maxTries: typeof n.maxTries === 'number' ? n.maxTries : null,
    })
    nameToId.set(nName, nId)
    nameToId.set(nId, nId)
    typeByName.set(nName, nType)
  })

  const edges: N8nGraphEdge[] = []
  const connCounts: Record<string, number> = {}
  const connections =
    doc.connections && typeof doc.connections === 'object'
      ? (doc.connections as Record<string, Record<string, unknown[][]>>)
      : {}

  let edgeI = 0
  for (const [sourceName, connBlock] of Object.entries(connections)) {
    if (!connBlock || typeof connBlock !== 'object') continue
    const sourceId = nameToId.get(sourceName)
    if (!sourceId) {
      warnings.push(`Connection source '${sourceName}' has no matching node`)
      continue
    }
    const sourceType = typeByName.get(sourceName) || 'unknown'
    for (const [ctype, groups] of Object.entries(connBlock)) {
      if (!Array.isArray(groups)) continue
      groups.forEach((group, sourceIndex) => {
        if (!Array.isArray(group)) return
        for (const link of group) {
          if (!link || typeof link !== 'object') continue
          const L = link as { node?: string; type?: string; index?: number }
          const targetName = String(L.node || '')
          const targetId = nameToId.get(targetName)
          if (!targetId) {
            warnings.push(
              `Connection target '${targetName}' from '${sourceName}' has no matching node`,
            )
            continue
          }
          const connectionType = String(L.type || ctype)
          edges.push({
            id: `e-${edgeI++}`,
            source: sourceId,
            target: targetId,
            sourceName,
            targetName,
            connectionType,
            sourceIndex,
            targetIndex: Number(L.index) || 0,
            sourceHandle: sourceHandle(ctype, sourceIndex, sourceType),
          })
          connCounts[ctype] = (connCounts[ctype] || 0) + 1
        }
      })
    }
  }

  const report: N8nImportReport = {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    supportedTypes: [...supportedTypes].sort(),
    unsupportedTypes: [...unsupportedTypes].sort(),
    credentialRequirements: [...credMap.values()],
    triggerSummary: triggerSummary(nodes.map((n) => n.type)),
    connectionTypeCounts: connCounts,
    warnings,
  }

  return {
    name: String(doc.name || 'Imported n8n workflow'),
    active: Boolean(doc.active),
    settings:
      doc.settings && typeof doc.settings === 'object'
        ? (doc.settings as Record<string, unknown>)
        : {},
    pinData:
      doc.pinData && typeof doc.pinData === 'object'
        ? (doc.pinData as Record<string, unknown>)
        : {},
    nodes,
    edges,
    report,
  }
}

/** Map category → legacy palette kind for demo seeds */
export function categoryToLegacyKind(cat: WfCategory): WfNodeKind {
  switch (cat) {
    case 'trigger':
      return 'trigger'
    case 'ai':
      return 'llm'
    case 'output':
      return 'notify'
    case 'logic':
      return 'condition'
    case 'input':
      return 'http'
    case 'transform':
      return 'code'
    case 'data':
      return 'http'
    default:
      return 'unknown'
  }
}
