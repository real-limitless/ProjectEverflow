import { useCallback, useState } from 'react'
import { Button, Pagination, TextInput } from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  ApiError,
  createKnowledgeCanvas,
  isDemoMode,
  reindexKnowledgeCanvas,
  searchKnowledgeWeb,
} from '@/lib/api'
import { mapApiCanvas } from '@/lib/studioMap'
import { pushToast } from '@/lib/studioToast'
import { useStudioDemoStore } from '@/store/studioDemoStore'
import type { WebSearchHit } from '@/types/studio'
import { ReaderMode } from './ReaderMode'

interface WebSearchTabProps {
  projectId: string
}

function truncateName(name: string, max = 200): string {
  const t = name.trim() || 'Untitled'
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`
}

const DEFAULT_PAGE_SIZE = 10

export function WebSearchTab({ projectId }: WebSearchTabProps) {
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const createCanvas = useStudioDemoStore((s) => s.createCanvas)
  const updateCanvas = useStudioDemoStore((s) => s.updateCanvas)
  const replaceCanvases = useStudioDemoStore((s) => s.update)

  const [searchQ, setSearchQ] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [hits, setHits] = useState<WebSearchHit[]>([])
  const [readerId, setReaderId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [hasMore, setHasMore] = useState(false)

  const reader = hits.find((h) => h.id === readerId) ?? null

  // Approximate itemCount for PatternFly Pagination (SearXNG has no total).
  const itemCount = hasMore
    ? page * pageSize + 1
    : Math.max((page - 1) * pageSize + hits.length, hits.length)

  const runSearch = async (opts?: { page?: number; pageSize?: number; query?: string }) => {
    const q = (opts?.query ?? searchQ).trim()
    const nextPage = opts?.page ?? 1
    const nextSize = opts?.pageSize ?? pageSize
    if (!q) {
      setHits([])
      setError(null)
      setReaderId(null)
      setActiveQuery('')
      setHasMore(false)
      setPage(1)
      return
    }
    setLoading(true)
    setError(null)
    setReaderId(null)
    try {
      const envelope = await searchKnowledgeWeb(projectId, q, {
        page: nextPage,
        pageSize: nextSize,
      })
      setActiveQuery(envelope.query || q)
      setPage(envelope.page || nextPage)
      setPageSize(envelope.page_size || nextSize)
      setHasMore(Boolean(envelope.has_more))
      setHits(
        (envelope.results || []).map((r) => ({
          id: r.id,
          title: r.title,
          url: r.url,
          snippet: r.snippet,
          readerMarkdown: r.reader_markdown || undefined,
        })),
      )
    } catch (e) {
      setHits([])
      setHasMore(false)
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

  const onContentLoaded = useCallback(
    (
      hitId: string,
      markdown: string,
      title?: string,
      method?: WebSearchHit['extractMethod'],
    ) => {
      setHits((prev) =>
        prev.map((h) =>
          h.id === hitId
            ? {
                ...h,
                readerMarkdown: markdown,
                ...(title ? { title } : {}),
                ...(method ? { extractMethod: method } : {}),
              }
            : h,
        ),
      )
    },
    [],
  )

  const runDemoPipeline = (id: string) => {
    updateCanvas(projectId, id, { status: 'chunking', chunks: 0 })
    window.setTimeout(() => updateCanvas(projectId, id, { status: 'embedding' }), 600)
    window.setTimeout(() => {
      updateCanvas(projectId, id, {
        status: 'indexed',
        chunks: 18 + Math.floor(Math.random() * 40),
      })
    }, 1400)
  }

  const addToKnowledge = async (hit: WebSearchHit) => {
    const md =
      hit.readerMarkdown ||
      `# ${hit.title}\n\nSource: ${hit.url}\n\n${hit.snippet}\n`
    const name = truncateName(hit.title)

    if (useApi) {
      if (adding) return
      setAdding(true)
      try {
        const created = await createKnowledgeCanvas(projectId, {
          name,
          description: hit.url,
          content_md: md,
          origin: 'web',
          source_url: hit.url,
        })
        const mapped = mapApiCanvas(created)
        replaceCanvases(projectId, (s) => ({
          ...s,
          canvases: [mapped, ...s.canvases.filter((c) => c.id !== mapped.id)],
        }))
        try {
          const indexed = await reindexKnowledgeCanvas(projectId, mapped.id)
          replaceCanvases(projectId, (s) => ({
            ...s,
            canvases: s.canvases.map((c) =>
              c.id === mapped.id ? mapApiCanvas(indexed) : c,
            ),
          }))
        } catch {
          // Canvas saved; reindex may be unavailable until Phase 1 backend is up
          runDemoPipeline(mapped.id)
        }
        pushToast('Added to knowledge', {
          description: 'Pinned reader text as a canvas and started embed pipeline',
          kind: 'success',
        })
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Add to knowledge failed', {
          kind: 'danger',
        })
      } finally {
        setAdding(false)
      }
      return
    }

    const id = createCanvas(projectId, {
      name,
      contentMd: md,
      origin: 'web',
      desc: hit.url,
    })
    runDemoPipeline(id)
    pushToast('Added to knowledge', {
      description: 'Pinned reader text as a canvas and started embed pipeline',
      kind: 'success',
    })
  }

  if (reader) {
    return (
      <ReaderMode
        hit={reader}
        projectId={projectId}
        onBack={() => setReaderId(null)}
        onAddToKnowledge={(h) => void addToKnowledge(h)}
        onContentLoaded={onContentLoaded}
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
            if (e.key === 'Enter') void runSearch({ page: 1 })
          }}
          aria-label="Web search query"
          isDisabled={loading}
        />
        <Button
          variant="primary"
          onClick={() => void runSearch({ page: 1 })}
          isLoading={loading}
        >
          Search
        </Button>
      </div>
      {error ? (
        <div
          className="lc-meta"
          role="alert"
          style={{
            marginBottom: 12,
            color: 'var(--pf-t--global--text--color--status--danger--default, #c9190b)',
          }}
        >
          {error}
        </div>
      ) : null}
      {!loading && hits.length === 0 && !error ? (
        <EmptySplash
          title="Web search"
          body="Run a query, open a hit to read the full article (extracted text) or view the live website, then pin it to Knowledge. Follow links in Reader and use browser extract when plain HTML fails."
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
                Open
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => window.open(h.url, '_blank', 'noopener,noreferrer')}
              >
                Open original
              </Button>
              <Button
                size="sm"
                variant="link"
                isInline
                isDisabled={adding}
                onClick={() => void addToKnowledge(h)}
              >
                Add to knowledge
              </Button>
            </div>
          </div>
        ))}
      {!loading && activeQuery && hits.length > 0 ? (
        <div className="knowledge-web-pagination">
          <Pagination
            itemCount={itemCount}
            perPage={pageSize}
            page={page}
            onSetPage={(_e, p) => void runSearch({ page: p, query: activeQuery })}
            onPerPageSelect={(_e, per) =>
              void runSearch({ page: 1, pageSize: per, query: activeQuery })
            }
            perPageOptions={[
              { title: '10', value: 10 },
              { title: '20', value: 20 },
              { title: '30', value: 30 },
            ]}
            variant="bottom"
            isDisabled={loading}
            titles={{
              paginationAriaLabel: 'Web search results pagination',
            }}
          />
          <span className="knowledge-web-page-indicator">
            Page {page}
            {hasMore ? ' · more available' : ''}
          </span>
        </div>
      ) : null}
    </div>
  )
}
