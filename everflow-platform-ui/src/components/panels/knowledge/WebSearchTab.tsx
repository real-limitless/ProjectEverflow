import { useState } from 'react'
import { Button, TextInput } from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { ApiError, searchKnowledgeWeb } from '@/lib/api'
import { pushToast } from '@/lib/studioToast'
import { useStudioDemoStore } from '@/store/studioDemoStore'
import type { WebSearchHit } from '@/types/studio'
import { ReaderMode } from './ReaderMode'

interface WebSearchTabProps {
  projectId: string
}

export function WebSearchTab({ projectId }: WebSearchTabProps) {
  const createCanvas = useStudioDemoStore((s) => s.createCanvas)
  const updateCanvas = useStudioDemoStore((s) => s.updateCanvas)

  const [searchQ, setSearchQ] = useState('')
  const [hits, setHits] = useState<WebSearchHit[]>([])
  const [readerId, setReaderId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reader = hits.find((h) => h.id === readerId) ?? null

  const runSearch = async () => {
    const q = searchQ.trim()
    if (!q) {
      setHits([])
      setError(null)
      setReaderId(null)
      return
    }
    setLoading(true)
    setError(null)
    setReaderId(null)
    try {
      const results = await searchKnowledgeWeb(projectId, q)
      setHits(results)
    } catch (e) {
      setHits([])
      setError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Web search failed',
      )
    } finally {
      setLoading(false)
    }
  }

  const addToKnowledge = (hit: WebSearchHit) => {
    const md =
      hit.readerMarkdown ||
      `# ${hit.title}\n\nSource: ${hit.url}\n\n${hit.snippet}\n`
    const id = createCanvas(projectId, {
      name: hit.title,
      contentMd: md,
      origin: 'web',
      desc: hit.url,
    })
    updateCanvas(projectId, id, { status: 'chunking', chunks: 0 })
    window.setTimeout(() => updateCanvas(projectId, id, { status: 'embedding' }), 600)
    window.setTimeout(() => {
      updateCanvas(projectId, id, {
        status: 'indexed',
        chunks: 18 + Math.floor(Math.random() * 40),
      })
    }, 1400)
    pushToast('Added to knowledge', {
      description: 'Pinned reader text as a canvas and started embed pipeline',
      kind: 'success',
    })
  }

  if (reader) {
    return (
      <ReaderMode
        hit={reader}
        onBack={() => setReaderId(null)}
        onAddToKnowledge={addToKnowledge}
      />
    )
  }

  return (
    <div className="knowledge-web-tab">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <TextInput
          value={searchQ}
          onChange={(_e, v) => setSearchQ(v)}
          placeholder="Search the web…"
          onKeyDown={(e) => {
            if (e.key === 'Enter') void runSearch()
          }}
          aria-label="Web search query"
          isDisabled={loading}
        />
        <Button variant="primary" onClick={() => void runSearch()} isLoading={loading}>
          Search
        </Button>
      </div>
      {error ? (
        <div className="lc-meta" role="alert" style={{ marginBottom: 12, color: 'var(--pf-t--global--text--color--status--danger--default, #c9190b)' }}>
          {error}
        </div>
      ) : null}
      {!loading && hits.length === 0 && !error ? (
        <EmptySplash
          title="Web search"
          body="Run a query, open a hit in Reader mode (clean Markdown, no ads), then summarize, research, or pin it to Knowledge for the main chatbot."
        />
      ) : null}
      {loading ? <div className="lc-meta">Searching…</div> : null}
      {!loading &&
        hits.map((h) => (
          <div className="list-card" key={h.id}>
            <div className="lc-title">{h.title}</div>
            <div className="lc-meta">{h.url}</div>
            <div className="lc-meta" style={{ marginTop: 4 }}>
              {h.snippet}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <Button size="sm" variant="primary" onClick={() => setReaderId(h.id)}>
                Open in Reader
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => window.open(h.url, '_blank', 'noopener,noreferrer')}
              >
                Open original
              </Button>
              <Button size="sm" variant="link" isInline onClick={() => addToKnowledge(h)}>
                Add to knowledge
              </Button>
            </div>
          </div>
        ))}
    </div>
  )
}
