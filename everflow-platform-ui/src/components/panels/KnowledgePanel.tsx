import { useMemo, useRef, useState } from 'react'
import {
  Button,
  FormGroup,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { EmbedStatus, WebSearchHit } from '@/types/studio'

const EMBED_STEPS: EmbedStatus[] = ['uploading', 'chunking', 'embedding', 'indexed']

function EmbedPipeline({ status }: { status: EmbedStatus }) {
  const idx = EMBED_STEPS.indexOf(status === 'error' ? 'uploading' : status)
  return (
    <div className="embed-pipeline">
      {EMBED_STEPS.map((step, i) => (
        <span
          key={step}
          className={`embed-step ${i < idx ? 'is-done' : i === idx ? 'is-active' : ''}`}
        >
          {step}
        </span>
      ))}
    </div>
  )
}

const DEMO_SEARCH: WebSearchHit[] = [
  {
    id: 'ws1',
    title: 'Podman compose remote deploy',
    url: 'https://docs.example.com/podman-compose',
    snippet: 'Run compose files on a remote host with SSH and rootless Podman…',
  },
  {
    id: 'ws2',
    title: 'pgvector embeddings for RAG',
    url: 'https://docs.example.com/pgvector',
    snippet: 'Chunk documents, embed with your model, store vectors for retrieval…',
  },
  {
    id: 'ws3',
    title: 'n8n workflow import format',
    url: 'https://docs.n8n.io/workflows/export-import/',
    snippet: 'Export workflows as JSON and map nodes when importing…',
  },
]

export function KnowledgePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const state = useProjectStudio(projectId)
  const addDoc = useStudioDemoStore((s) => s.addDoc)
  const createMindMap = useStudioDemoStore((s) => s.createMindMap)
  const addMindNode = useStudioDemoStore((s) => s.addMindNode)

  const [sub, setSub] = useState<'canvas' | 'web' | 'mind'>('canvas')
  const [activeCanvas, setActiveCanvas] = useState(state.canvases[0]?.id ?? '')
  const [searchQ, setSearchQ] = useState('')
  const [hits, setHits] = useState<WebSearchHit[]>([])
  const [mapOpen, setMapOpen] = useState(false)
  const [mapName, setMapName] = useState('')
  const [nodeLabel, setNodeLabel] = useState('')
  const [activeMap, setActiveMap] = useState(state.mindMaps[0]?.id ?? '')
  const fileRef = useRef<HTMLInputElement>(null)

  const canvas = state.canvases.find((c) => c.id === activeCanvas) ?? state.canvases[0]
  const docs = useMemo(
    () => state.docs.filter((d) => !canvas || d.canvasId === canvas.id || !d.canvasId),
    [state.docs, canvas],
  )
  const mind = state.mindMaps.find((m) => m.id === activeMap) ?? state.mindMaps[0]

  const onUpload = (files: FileList | null) => {
    if (!files?.length) return
    Array.from(files).forEach((f) => {
      addDoc(projectId, {
        name: f.name,
        mime: f.type || 'application/octet-stream',
        sizeLabel: f.size > 1e6 ? `${(f.size / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(f.size / 1024))} KB`,
        canvasId: canvas?.id,
      })
    })
    pushToast('Indexing documents', {
      description: 'Demo pipeline: upload → chunk → embed → vector store',
      kind: 'info',
    })
  }

  const runSearch = () => {
    const q = searchQ.trim().toLowerCase()
    if (!q) {
      setHits([])
      return
    }
    setHits(
      DEMO_SEARCH.filter(
        (h) =>
          h.title.toLowerCase().includes(q) ||
          h.snippet.toLowerCase().includes(q) ||
          q.split(/\s+/).some((w) => h.snippet.toLowerCase().includes(w)),
      ).length
        ? DEMO_SEARCH.filter(
            (h) =>
              h.title.toLowerCase().includes(q) ||
              h.snippet.toLowerCase().includes(q) ||
              true,
          ).slice(0, 3)
        : DEMO_SEARCH,
    )
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
          <Tab eventKey="web" title={<TabTitleText>Web search</TabTitleText>} />
          <Tab eventKey="mind" title={<TabTitleText>Mind maps</TabTitleText>} />
        </Tabs>
      </div>
      <div className="panel-scroll">
        {sub === 'canvas' && (
          <>
            <div className="section-label">Canvases</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {state.canvases.map((c) => (
                <Button
                  key={c.id}
                  size="sm"
                  variant={c.id === canvas?.id ? 'primary' : 'secondary'}
                  onClick={() => setActiveCanvas(c.id)}
                >
                  {c.name}
                </Button>
              ))}
            </div>
            {canvas && (
              <div className="list-card">
                <div className="lc-title">{canvas.name}</div>
                <div className="lc-meta">{canvas.desc}</div>
                <p className="lc-meta" style={{ marginTop: 8 }}>
                  Upload large documents (PDF, text). Everflow embeds them into a vector store so the
                  chatbot can retrieve this knowledge in conversation.
                </p>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md,.doc,.docx"
                  style={{ display: 'none' }}
                  onChange={(e) => onUpload(e.target.files)}
                />
                <Button
                  variant="primary"
                  size="sm"
                  style={{ marginTop: 8 }}
                  onClick={() => fileRef.current?.click()}
                >
                  Upload documents
                </Button>
              </div>
            )}
            <div className="section-label">Indexed documents</div>
            {docs.length === 0 ? (
              <EmptySplash
                title="No documents on this canvas"
                body="Upload a PDF or text file to embed into the project vector store (demo)."
                primaryLabel="Upload"
                onPrimary={() => fileRef.current?.click()}
              />
            ) : (
              docs.map((d) => (
                <div className="list-card" key={d.id}>
                  <div className="lc-row">
                    <div className="lc-title">{d.name}</div>
                    <span className="pill">{d.sizeLabel}</span>
                  </div>
                  <EmbedPipeline status={d.status} />
                  <div className="lc-meta">
                    {d.status === 'indexed'
                      ? `${d.chunks ?? 0} chunks · available to chatbot via vector store`
                      : `Status: ${d.status}`}
                  </div>
                </div>
              ))
            )}
          </>
        )}

        {sub === 'web' && (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <TextInput
                value={searchQ}
                onChange={(_e, v) => setSearchQ(v)}
                placeholder="Search the web (demo results)…"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') runSearch()
                }}
                aria-label="Web search query"
              />
              <Button variant="primary" onClick={runSearch}>
                Search
              </Button>
            </div>
            {hits.length === 0 ? (
              <EmptySplash
                title="Web search"
                body="Run a query to pull demo search hits you can later pin to a canvas."
              />
            ) : (
              hits.map((h) => (
                <div className="list-card" key={h.id}>
                  <div className="lc-title">{h.title}</div>
                  <div className="lc-meta">{h.url}</div>
                  <div className="lc-meta" style={{ marginTop: 4 }}>
                    {h.snippet}
                  </div>
                </div>
              ))
            )}
          </>
        )}

        {sub === 'mind' && (
          <>
            <div className="panel-toolbar" style={{ border: 'none', paddingInline: 0 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {state.mindMaps.map((m) => (
                  <Button
                    key={m.id}
                    size="sm"
                    variant={m.id === mind?.id ? 'primary' : 'secondary'}
                    onClick={() => setActiveMap(m.id)}
                  >
                    {m.name}
                  </Button>
                ))}
              </div>
              <Button size="sm" variant="primary" onClick={() => setMapOpen(true)}>
                New mind map
              </Button>
            </div>
            {!mind ? (
              <EmptySplash
                title="No mind maps"
                body="Create a mind map to organize concepts for this project."
                primaryLabel="New mind map"
                onPrimary={() => setMapOpen(true)}
              />
            ) : (
              <>
                <div className="mind-map-tree">
                  {mind.nodes.map((n) => (
                    <div
                      key={n.id}
                      className={`mind-map-node ${n.parentId == null ? 'is-root' : ''}`}
                      style={{
                        marginInlineStart: n.parentId == null ? 0 : 16 + depthOf(mind.nodes, n.id) * 12,
                      }}
                    >
                      {n.label}
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <TextInput
                    value={nodeLabel}
                    onChange={(_e, v) => setNodeLabel(v)}
                    placeholder="Add child node under root…"
                    aria-label="Mind map node"
                  />
                  <Button
                    onClick={() => {
                      if (!nodeLabel.trim() || !mind) return
                      const root = mind.nodes.find((n) => n.parentId == null)
                      addMindNode(projectId, mind.id, nodeLabel.trim(), root?.id ?? null)
                      setNodeLabel('')
                    }}
                  >
                    Add node
                  </Button>
                </div>
              </>
            )}
          </>
        )}
      </div>

      <CreateResourceModal
        isOpen={mapOpen}
        title="Create mind map"
        onClose={() => setMapOpen(false)}
        onSubmit={() => {
          if (!mapName.trim()) return
          createMindMap(projectId, mapName.trim())
          pushToast('Mind map created', { kind: 'success' })
          setMapName('')
          setMapOpen(false)
        }}
        isSubmitDisabled={!mapName.trim()}
      >
        <FormGroup label="Name" isRequired fieldId="mm-name">
          <TextInput id="mm-name" value={mapName} onChange={(_e, v) => setMapName(v)} />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}

function depthOf(
  nodes: { id: string; parentId: string | null }[],
  id: string,
  seen = new Set<string>(),
): number {
  const n = nodes.find((x) => x.id === id)
  if (!n || !n.parentId || seen.has(id)) return 0
  seen.add(id)
  return 1 + depthOf(nodes, n.parentId, seen)
}
