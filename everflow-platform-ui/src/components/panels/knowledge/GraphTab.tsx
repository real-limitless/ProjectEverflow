import { useCallback, useEffect, useState } from 'react'
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

interface GraphTabProps {
  projectId: string
}

type GraphNode = {
  key: string
  label: string
  kind: string
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
            n.push({ key: wk, label: c.source_url.slice(0, 56), kind: 'web' })
          }
        }
        if (c.repo_path) {
          const rk = `repo:${c.repo_path}`
          if (!n.some((x) => x.key === rk)) {
            n.push({ key: rk, label: c.repo_path, kind: 'repo' })
          }
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
        body="Pin web sources, index the repo, or promote research threads to see canvases, agents, and sources linked here."
      />
    )
  }

  return (
    <div className="knowledge-graph-tab">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <p className="lc-meta">
          {nodes.length} nodes · {edges.length} edges
        </p>
        <Button size="sm" variant="secondary" onClick={() => void load()}>
          Refresh
        </Button>
      </div>
      <div className="knowledge-graph-nodes" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {nodes.map((n) => (
          <div
            key={n.key}
            className="list-card"
            style={{ minWidth: 140, maxWidth: 220, padding: 10 }}
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
          {edges.slice(0, 80).map((e, i) => (
            <div key={`${e.from}-${e.to}-${i}`} className="lc-meta" style={{ marginBottom: 4 }}>
              <code>{e.from}</code> —{e.rel}→ <code>{e.to}</code>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
