import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Spinner } from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  isDemoMode,
  listKnowledgeCanvases,
  listKnowledgeLinks,
  listProjectAgents,
} from '@/lib/api'
import { pushToast } from '@/lib/studioToast'
import { useProjectStudio } from '@/store/studioDemoStore'
import { MermaidView } from './MermaidView'

interface GraphTabProps {
  projectId: string
}

type GraphNode = {
  key: string
  label: string
  kind: string
}

function sanitizeMermaidId(key: string): string {
  return `n_${key.replace(/[^a-zA-Z0-9_]/g, '_').slice(0, 48)}`
}

function escapeLabel(label: string): string {
  return label.replace(/"/g, "'").replace(/\n/g, ' ').slice(0, 40)
}

function buildMermaid(
  nodes: GraphNode[],
  edges: { from: string; to: string; rel: string }[],
  limit = 40,
): string {
  const limited = nodes.slice(0, limit)
  const keys = new Set(limited.map((n) => n.key))
  const lines = ['flowchart LR']
  const idMap = new Map<string, string>()
  for (const n of limited) {
    const id = sanitizeMermaidId(n.key)
    idMap.set(n.key, id)
    const shape =
      n.kind === 'agent'
        ? `[[${escapeLabel(n.label)}]]`
        : n.kind === 'web' || n.kind === 'repo'
          ? `([${escapeLabel(n.label)}])`
          : `[${escapeLabel(n.label)}]`
    lines.push(`  ${id}${shape}`)
    lines.push(`  class ${id} kind_${n.kind}`)
  }
  for (const e of edges) {
    if (!keys.has(e.from) || !keys.has(e.to)) continue
    const a = idMap.get(e.from)
    const b = idMap.get(e.to)
    if (!a || !b) continue
    const rel = escapeLabel(e.rel || 'link')
    lines.push(`  ${a} -->|${rel}| ${b}`)
  }
  lines.push('  classDef kind_canvas fill:#dbeafe,stroke:#3b82f6,color:#1e3a5f')
  lines.push('  classDef kind_agent fill:#fce7f3,stroke:#db2777,color:#831843')
  lines.push('  classDef kind_web fill:#d1fae5,stroke:#059669,color:#064e3b')
  lines.push('  classDef kind_repo fill:#fef3c7,stroke:#d97706,color:#78350f')
  lines.push('  classDef kind_mindmap fill:#e0e7ff,stroke:#6366f1,color:#312e81')
  return lines.join('\n')
}

export function GraphTab({ projectId }: GraphTabProps) {
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()
  const demo = useProjectStudio(projectId)

  const [loading, setLoading] = useState(false)
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<
    { from: string; to: string; rel: string }[]
  >([])

  const load = useCallback(async () => {
    if (!useApi) {
      const n: GraphNode[] = [
        ...demo.canvases.map((c) => ({
          key: `canvas:${c.id}`,
          label: c.name,
          kind: 'canvas',
        })),
        ...demo.mindMaps.map((m) => ({
          key: `mindmap:${m.id}`,
          label: m.name,
          kind: 'mindmap',
        })),
      ]
      const e: { from: string; to: string; rel: string }[] = []
      for (const c of demo.canvases) {
        if (c.origin === 'web' && c.desc) {
          const wk = `web:${c.desc.slice(0, 40)}`
          n.push({ key: wk, label: c.desc.slice(0, 48), kind: 'web' })
          e.push({ from: wk, to: `canvas:${c.id}`, rel: 'derived_from' })
        }
      }
      setNodes(n)
      setEdges(e)
      return
    }

    setLoading(true)
    try {
      const [canvases, links, agents] = await Promise.all([
        listKnowledgeCanvases(projectId),
        listKnowledgeLinks(projectId),
        listProjectAgents(projectId).catch(() => []),
      ])
      const canvasName = new Map(canvases.map((c) => [c.id, c.name]))
      const agentName = new Map(agents.map((a) => [a.id, a.name]))

      const n: GraphNode[] = [
        ...canvases.map((c) => ({
          key: `canvas:${c.id}`,
          label: c.name,
          kind: 'canvas',
        })),
        ...agents.map((a) => ({
          key: `agent:${a.id}`,
          label: a.name,
          kind: 'agent',
        })),
      ]
      for (const c of canvases) {
        if (c.source_url) {
          const wk = `web:${c.source_url.slice(0, 48)}`
          if (!n.some((x) => x.key === wk)) {
            n.push({
              key: wk,
              label: c.source_url.replace(/^https?:\/\//, '').slice(0, 56),
              kind: 'web',
            })
          }
        }
        if (c.repo_path) {
          const rk = `repo:${c.repo_path}`
          if (!n.some((x) => x.key === rk)) {
            n.push({ key: rk, label: c.repo_path, kind: 'repo' })
          }
        }
      }

      const resolveLabel = (type: string, id: string) => {
        if (type === 'canvas') return canvasName.get(id) || id.slice(0, 8)
        if (type === 'agent') return agentName.get(id) || id.slice(0, 8)
        if (type === 'web') return id.replace(/^https?:\/\//, '').slice(0, 40)
        if (type === 'repo' || type === 'repo_path') return id.slice(0, 40)
        return id.slice(0, 24)
      }

      // Ensure linked endpoints exist as nodes with readable labels
      for (const l of links) {
        const fromKey = `${l.from_type}:${l.from_id}`
        const toKey = `${l.to_type}:${l.to_id}`
        if (!n.some((x) => x.key === fromKey)) {
          n.push({
            key: fromKey,
            label: resolveLabel(l.from_type, l.from_id),
            kind: l.from_type === 'repo_path' ? 'repo' : l.from_type,
          })
        }
        if (!n.some((x) => x.key === toKey)) {
          n.push({
            key: toKey,
            label: resolveLabel(l.to_type, l.to_id),
            kind: l.to_type === 'repo_path' ? 'repo' : l.to_type,
          })
        }
      }

      setNodes(n)
      setEdges(
        links.map((l) => ({
          from: `${l.from_type}:${l.from_id}`,
          to: `${l.to_type}:${l.to_id}`,
          rel: l.rel,
        })),
      )
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load graph', {
        kind: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [demo.canvases, demo.mindMaps, projectId, useApi])

  useEffect(() => {
    void load()
  }, [load])

  const mermaid = useMemo(() => buildMermaid(nodes, edges), [nodes, edges])

  if (loading) {
    return (
      <div className="reader-mode-loading">
        <Spinner size="lg" />
        <span>Loading knowledge graph…</span>
      </div>
    )
  }

  if (!nodes.length) {
    return (
      <EmptySplash
        title="Knowledge graph"
        body="Relationships appear here when you index the repo, pin web pages, or promote research. Canvases, sources, and agents are linked so you can see what feeds retrieval."
      />
    )
  }

  const kindCounts = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.kind] = (acc[n.kind] || 0) + 1
    return acc
  }, {})

  return (
    <div className="knowledge-graph-tab">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <p className="lc-meta" style={{ margin: 0 }}>
            {nodes.length} nodes · {edges.length} links
          </p>
          <p className="lc-meta" style={{ margin: '4px 0 0' }}>
            {Object.entries(kindCounts)
              .map(([k, v]) => `${k}: ${v}`)
              .join(' · ')}
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      <div className="knowledge-graph-diagram" style={{ minHeight: 280, marginBottom: 16 }}>
        <MermaidView source={mermaid} />
      </div>

      {nodes.length > 40 ? (
        <p className="lc-meta">Showing first 40 nodes in the diagram. Full list below.</p>
      ) : null}

      <div className="knowledge-graph-nodes" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {nodes.map((n) => (
          <div
            key={n.key}
            className="list-card"
            style={{ minWidth: 140, maxWidth: 220, padding: 10 }}
            title={n.key}
          >
            <div className="lc-meta" style={{ textTransform: 'uppercase', fontSize: 11 }}>
              {n.kind}
            </div>
            <div className="lc-title" style={{ fontSize: 13 }}>
              {n.label}
            </div>
          </div>
        ))}
      </div>

      {edges.length ? (
        <div style={{ marginTop: 16 }}>
          <div className="lc-title" style={{ marginBottom: 8 }}>
            Links
          </div>
          {edges.slice(0, 80).map((e, i) => {
            const from = nodes.find((n) => n.key === e.from)
            const to = nodes.find((n) => n.key === e.to)
            return (
              <div key={`${e.from}-${e.to}-${i}`} className="lc-meta" style={{ marginBottom: 4 }}>
                <strong>{from?.label || e.from}</strong>
                {' —'}
                {e.rel}
                {'→ '}
                <strong>{to?.label || e.to}</strong>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="lc-meta" style={{ marginTop: 12 }}>
          No explicit links yet. Indexing repo docs and adding web sources creates derived_from
          links automatically.
        </p>
      )}
    </div>
  )
}
