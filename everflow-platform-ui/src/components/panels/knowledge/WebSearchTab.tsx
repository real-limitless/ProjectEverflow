import { useState } from 'react'
import { Button, TextInput } from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { pushToast } from '@/lib/studioToast'
import { useStudioDemoStore } from '@/store/studioDemoStore'
import type { WebSearchHit } from '@/types/studio'
import { DEMO_SEARCH } from './demoKnowledge'
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

  const reader = hits.find((h) => h.id === readerId) ?? null

  const runSearch = () => {
    const q = searchQ.trim().toLowerCase()
    if (!q) {
      setHits([])
      setReaderId(null)
      return
    }
    const filtered = DEMO_SEARCH.filter(
      (h) =>
        h.title.toLowerCase().includes(q) ||
        h.snippet.toLowerCase().includes(q) ||
        h.url.toLowerCase().includes(q) ||
        q.split(/\s+/).some((w) => w.length > 2 && h.snippet.toLowerCase().includes(w)),
    )
    setHits(filtered.length ? filtered : DEMO_SEARCH)
    setReaderId(null)
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
          body="Run a query, open a hit in Reader mode (clean Markdown, no ads), then summarize, research, or pin it to Knowledge for the main chatbot."
        />
      ) : (
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
        ))
      )}
    </div>
  )
}
