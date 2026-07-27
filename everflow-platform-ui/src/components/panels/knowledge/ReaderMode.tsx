import {
  Button,
  Spinner,
  TextInput,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { useCallback, useEffect, useRef, useState } from 'react'
import { getProject } from '@/data/projects'
import {
  ApiError,
  fetchKnowledgeWebRead,
  isDemoMode,
  promoteResearchToCanvas,
  type ApiWebReadMethod,
  type ApiWebReadMode,
} from '@/lib/api'
import { markdownToHtml } from '@/lib/chatMarkdown'
import {
  endResearchSession,
  researchChatTurn,
  startResearchSession,
  summarizeArticleWithOpenCode,
} from '@/lib/knowledge/researchChat'
import { pushToast } from '@/lib/studioToast'
import type { WebReadMethod, WebSearchHit } from '@/types/studio'
import { researchReply, summarizeReader } from './demoKnowledge'

interface ReaderModeProps {
  hit: WebSearchHit
  projectId: string
  onBack: () => void
  onAddToKnowledge: (hit: WebSearchHit) => void
  /** Persist extracted markdown onto the hit in the parent list */
  onContentLoaded?: (
    hitId: string,
    markdown: string,
    title?: string,
    method?: WebReadMethod,
  ) => void
}

interface ChatLine {
  role: 'user' | 'assistant'
  text: string
}

type ViewMode = 'reader' | 'website'

interface ReaderFrame {
  url: string
  title: string
  markdown: string
  method?: WebReadMethod
  warnings?: string[]
}

function methodLabel(m?: WebReadMethod): string {
  if (m === 'browser') return 'Browser'
  if (m === 'ocr') return 'OCR'
  if (m === 'http') return 'HTTP'
  return '…'
}

export function ReaderMode({
  hit,
  projectId,
  onBack,
  onAddToKnowledge,
  onContentLoaded,
}: ReaderModeProps) {
  const [view, setView] = useState<ViewMode>('reader')
  const [history, setHistory] = useState<ReaderFrame[]>([
    {
      url: hit.url,
      title: hit.title,
      markdown: hit.readerMarkdown || '',
      method: hit.extractMethod,
    },
  ])
  const [histIndex, setHistIndex] = useState(0)
  const frame = history[histIndex] ?? history[0]
  const [urlDraft, setUrlDraft] = useState(hit.url)
  const [loading, setLoading] = useState(!hit.readerMarkdown)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [summarizing, setSummarizing] = useState(false)
  const [researchOpen, setResearchOpen] = useState(false)
  const [chat, setChat] = useState<ChatLine[]>([])
  const [draft, setDraft] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [iframeFailed, setIframeFailed] = useState(false)
  const [promoting, setPromoting] = useState(false)
  const researchSessionRef = useRef<string | null>(null)
  const loadGenRef = useRef(0)
  const histIndexRef = useRef(0)
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const title = frame?.title || hit.title
  const markdown = frame?.markdown || ''
  const currentUrl = frame?.url || hit.url
  const extractMethod = frame?.method

  useEffect(() => {
    histIndexRef.current = histIndex
  }, [histIndex])

  const loadUrl = useCallback(
    async (
      url: string,
      opts?: {
        mode?: ApiWebReadMode
        /** Replace current history entry instead of pushing */
        replace?: boolean
        /** Jump to existing index without pushing */
        goIndex?: number
      },
    ) => {
      const target = url.trim()
      if (!target) return
      const gen = ++loadGenRef.current
      setLoading(true)
      setLoadError(null)
      setSummary(null)
      setIframeFailed(false)
      setUrlDraft(target)

      const applyFrame = (next: ReaderFrame) => {
        if (opts?.goIndex != null) {
          const idx = opts.goIndex
          histIndexRef.current = idx
          setHistIndex(idx)
          setHistory((h) => {
            const copy = [...h]
            copy[idx] = next
            return copy
          })
          return
        }
        if (opts?.replace) {
          setHistory((h) => {
            const copy = [...h]
            const idx = Math.min(histIndexRef.current, Math.max(0, copy.length - 1))
            copy[idx] = next
            return copy
          })
          return
        }
        setHistory((h) => {
          const idx = Math.min(histIndexRef.current, Math.max(0, h.length - 1))
          const truncated = h.slice(0, idx + 1)
          return [...truncated, next]
        })
        setHistIndex((i) => {
          const nextIdx = i + 1
          histIndexRef.current = nextIdx
          return nextIdx
        })
      }

      // Cached entry hit for the seed URL
      if (
        target === hit.url &&
        hit.readerMarkdown &&
        (!opts?.mode || opts.mode === 'auto' || opts.mode === 'http')
      ) {
        applyFrame({
          url: target,
          title: hit.title,
          markdown: hit.readerMarkdown,
          method: hit.extractMethod || 'http',
        })
        setLoading(false)
        return
      }

      try {
        const result = await fetchKnowledgeWebRead(projectId, target, {
          mode: opts?.mode ?? 'auto',
        })
        if (gen !== loadGenRef.current) return
        const method = (result.method || 'http') as ApiWebReadMethod
        const next: ReaderFrame = {
          url: result.url || target,
          title: result.title || target,
          markdown: result.markdown,
          method,
          warnings: result.warnings,
        }
        setUrlDraft(next.url)
        applyFrame(next)
        // Only cache onto parent list when still on the original search hit URL
        if (next.url === hit.url || target === hit.url) {
          onContentLoaded?.(hit.id, next.markdown, next.title, method)
        }
        if (result.warnings?.length) {
          // Soft notice — do not spam toasts on every thin escalate
          if (opts?.mode === 'browser' || opts?.mode === 'ocr') {
            pushToast(result.warnings.slice(-1)[0], { kind: 'info' })
          }
        }
      } catch (e) {
        if (gen !== loadGenRef.current) return
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : 'Failed to load page content'
        setLoadError(msg)
        applyFrame({
          url: target,
          title: target === hit.url ? hit.title : target,
          markdown:
            target === hit.url
              ? `# ${hit.title}\n\n${hit.snippet}\n\n_Could not extract full page text._\n\n[Open original](${hit.url})\n`
              : `# ${target}\n\n_Could not extract full page text._\n\n[Open original](${target})\n`,
        })
      } finally {
        if (gen === loadGenRef.current) setLoading(false)
      }
    },
    [hit, onContentLoaded, projectId],
  )

  // Initial load when opening a hit
  useEffect(() => {
    setView('reader')
    setSummary(null)
    setChat([])
    setDraft('')
    setIframeFailed(false)
    histIndexRef.current = 0
    setHistory([
      {
        url: hit.url,
        title: hit.title,
        markdown: hit.readerMarkdown || '',
        method: hit.extractMethod,
      },
    ])
    setHistIndex(0)
    setUrlDraft(hit.url)
    const prevSession = researchSessionRef.current
    researchSessionRef.current = null
    if (prevSession && useApi) {
      void endResearchSession(projectId, prevSession)
    }

    if (hit.readerMarkdown) {
      setLoading(false)
      setLoadError(null)
      return
    }

    void loadUrl(hit.url, { replace: true, goIndex: 0 })
    // Only re-init when the entry hit changes
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional seed load
  }, [hit.id, hit.url, projectId, useApi])

  useEffect(() => {
    return () => {
      const sid = researchSessionRef.current
      if (sid && useApi) void endResearchSession(projectId, sid)
    }
  }, [projectId, useApi])

  const body =
    markdown ||
    `# ${title}\n\n${hit.snippet}\n\n_No full reader text for this result._`

  const canBack = histIndex > 0
  const canForward = histIndex < history.length - 1

  const goBack = () => {
    if (!canBack) return
    const next = histIndex - 1
    histIndexRef.current = next
    setHistIndex(next)
    setUrlDraft(history[next]?.url || '')
    setLoadError(null)
    setSummary(null)
  }

  const goForward = () => {
    if (!canForward) return
    const next = histIndex + 1
    histIndexRef.current = next
    setHistIndex(next)
    setUrlDraft(history[next]?.url || '')
    setLoadError(null)
    setSummary(null)
  }

  const navigateTo = (url: string, mode?: ApiWebReadMode) => {
    void loadUrl(url, { mode })
  }

  const onReaderLinkClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = (e.target as HTMLElement | null)?.closest?.('a')
    if (!el) return
    const href = el.getAttribute('href')
    if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('javascript:')) {
      return
    }
    let absolute: string
    try {
      absolute = new URL(href, currentUrl).toString()
    } catch {
      return
    }
    if (!absolute.startsWith('http://') && !absolute.startsWith('https://')) {
      return
    }
    e.preventDefault()
    e.stopPropagation()
    setView('reader')
    navigateTo(absolute)
  }

  const runSummarize = async () => {
    if (loading || !markdown) return
    setSummarizing(true)
    try {
      if (useApi) {
        const text = await summarizeArticleWithOpenCode(projectId, title, body)
        setSummary(text)
      } else {
        setSummary(summarizeReader(title, body))
      }
    } catch (e) {
      setSummary(summarizeReader(title, body))
      pushToast(e instanceof Error ? e.message : 'Summary used offline fallback', {
        kind: 'warning',
      })
    } finally {
      setSummarizing(false)
    }
  }

  const ensureResearchSession = async () => {
    if (!useApi) return null
    if (researchSessionRef.current) return researchSessionRef.current
    const s = await startResearchSession(projectId, title)
    researchSessionRef.current = s.sessionId
    return s.sessionId
  }

  const sendResearch = async () => {
    const text = draft.trim()
    if (!text || chatBusy) return
    setDraft('')
    setChat((c) => [...c, { role: 'user', text }])
    setChatBusy(true)
    try {
      let reply: string
      if (useApi) {
        const sid = await ensureResearchSession()
        if (!sid) throw new Error('Could not start research session')
        reply = await researchChatTurn(projectId, sid, title, body, text)
      } else {
        reply = researchReply(text, title)
      }
      setChat((c) => [...c, { role: 'assistant', text: reply }])
    } catch (e) {
      const fallback = researchReply(text, title)
      setChat((c) => [
        ...c,
        {
          role: 'assistant',
          text:
            fallback +
            (e instanceof Error ? `\n\n_(Model unavailable: ${e.message})_` : ''),
        },
      ])
    } finally {
      setChatBusy(false)
    }
  }

  const enrichedHit: WebSearchHit = {
    ...hit,
    title,
    url: currentUrl,
    readerMarkdown: markdown || hit.readerMarkdown,
    extractMethod,
  }

  const promoteResearch = async (mode: 'thread' | 'claims') => {
    if (!chat.length) {
      pushToast('Chat first, then promote', { kind: 'warning' })
      return
    }
    if (!useApi) {
      onAddToKnowledge({
        ...enrichedHit,
        title: mode === 'claims' ? `Claims · ${title}` : `Research · ${title}`,
        readerMarkdown: chat
          .map((l) => `**${l.role === 'user' ? 'You' : 'Research'}:** ${l.text}`)
          .join('\n\n'),
      })
      return
    }
    setPromoting(true)
    try {
      await promoteResearchToCanvas(projectId, {
        title: (mode === 'claims' ? `Claims · ${title}` : `Research · ${title}`).slice(
          0,
          200,
        ),
        mode,
        source_url: currentUrl,
        article_title: title,
        thread: chat,
        article_markdown: markdown || hit.readerMarkdown || '',
      })
      pushToast(mode === 'claims' ? 'Claims saved to knowledge' : 'Thread saved to knowledge', {
        kind: 'success',
      })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Promote failed', { kind: 'danger' })
    } finally {
      setPromoting(false)
    }
  }

  const researchPanel = researchOpen ? (
    <div className="research-chat">
      <div className="research-chat-head">
        Ephemeral research chat · grounded on extracted article text
        {view === 'website' ? ' (not the live iframe)' : ''} · not the main Chat panel
      </div>
      <div className="research-chat-log">
        {chat.length === 0 ? (
          <p className="lc-meta">
            Ask to summarize, extract steps, or draft notes from this page. Pin to knowledge when
            you want it available to the main assistant.
          </p>
        ) : (
          chat.map((line, i) => (
            <div key={`${line.role}-${i}`} className={`research-chat-line is-${line.role}`}>
              <span className="research-chat-role">
                {line.role === 'user' ? 'You' : 'Research'}
              </span>
              <div
                className="knowledge-md"
                dangerouslySetInnerHTML={{
                  __html: markdownToHtml(line.text),
                }}
              />
            </div>
          ))
        )}
        {chatBusy ? <p className="lc-meta">Thinking…</p> : null}
      </div>
      <div className="research-chat-compose">
        <TextInput
          value={draft}
          onChange={(_e, v) => setDraft(v)}
          placeholder="Ask about this article…"
          aria-label="Research chat message"
          isDisabled={chatBusy}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void sendResearch()
          }}
        />
        <Button
          variant="primary"
          onClick={() => void sendResearch()}
          isDisabled={!draft.trim() || chatBusy}
          isLoading={chatBusy}
        >
          Send
        </Button>
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={!chat.length || promoting}
          isLoading={promoting}
          onClick={() => void promoteResearch('thread')}
        >
          Save thread as canvas
        </Button>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={!chat.length || promoting}
          onClick={() => void promoteResearch('claims')}
        >
          Extract claims → notes
        </Button>
      </div>
    </div>
  ) : null

  return (
    <div className={`reader-mode${researchOpen ? ' reader-mode--with-chat' : ''}`}>
      <div className="reader-mode-toolbar">
        <Button variant="link" isInline onClick={onBack}>
          ← Back to results
        </Button>
        <div className="reader-mode-actions">
          <ToggleGroup aria-label="Reader view mode">
            <ToggleGroupItem
              text="Reader"
              isSelected={view === 'reader'}
              onChange={() => setView('reader')}
            />
            <ToggleGroupItem
              text="Website"
              isSelected={view === 'website'}
              onChange={() => setView('website')}
            />
          </ToggleGroup>
          <Button
            size="sm"
            variant="secondary"
            isDisabled={loading || !markdown || summarizing}
            isLoading={summarizing}
            onClick={() => void runSummarize()}
          >
            Summarize
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setResearchOpen((o) => !o)}
          >
            {researchOpen ? 'Hide research chat' : 'Research chat'}
          </Button>
          <Button
            size="sm"
            variant="primary"
            isDisabled={loading}
            onClick={() => onAddToKnowledge(enrichedHit)}
          >
            Add to knowledge
          </Button>
        </div>
      </div>

      <div className="reader-mode-chrome" aria-label="Reader navigation">
        <Button
          size="sm"
          variant="secondary"
          isDisabled={!canBack || loading}
          onClick={goBack}
          aria-label="Back"
        >
          ←
        </Button>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={!canForward || loading}
          onClick={goForward}
          aria-label="Forward"
        >
          →
        </Button>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={loading}
          onClick={() => void loadUrl(currentUrl, { replace: true, mode: 'auto' })}
          aria-label="Reload"
        >
          ↻
        </Button>
        <TextInput
          className="reader-mode-url-input"
          value={urlDraft}
          onChange={(_e, v) => setUrlDraft(v)}
          aria-label="Page URL"
          isDisabled={loading}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              navigateTo(urlDraft.trim())
            }
          }}
        />
        <Button
          size="sm"
          variant="primary"
          isDisabled={loading || !urlDraft.trim()}
          onClick={() => navigateTo(urlDraft.trim())}
        >
          Go
        </Button>
        <span
          className={`reader-mode-method-badge method-${extractMethod || 'unknown'}`}
          title={frame?.warnings?.join('\n') || 'Extraction method'}
        >
          {methodLabel(extractMethod)}
        </span>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={loading}
          onClick={() => void loadUrl(currentUrl, { replace: true, mode: 'browser' })}
        >
          Browser extract
        </Button>
        <Button
          size="sm"
          variant="secondary"
          isDisabled={loading}
          onClick={() => void loadUrl(currentUrl, { replace: true, mode: 'ocr' })}
        >
          OCR
        </Button>
      </div>

      <div className="reader-mode-main">
        {view === 'website' ? (
          <div className="reader-mode-website">
            <div className="reader-mode-website-bar">
              <a className="reader-mode-url" href={currentUrl} target="_blank" rel="noreferrer">
                {currentUrl}
              </a>
              <Button
                size="sm"
                variant="link"
                isInline
                onClick={() => window.open(currentUrl, '_blank', 'noopener,noreferrer')}
              >
                Open in new tab
              </Button>
            </div>
            <p className="reader-mode-badge">
              Live site · some sites block embedding; research chat uses extracted Reader text
            </p>
            {iframeFailed ? (
              <div className="reader-mode-iframe-fallback">
                <p>This site could not be shown in an iframe (often blocked by the publisher).</p>
                <Button
                  variant="primary"
                  onClick={() => window.open(currentUrl, '_blank', 'noopener,noreferrer')}
                >
                  Open original
                </Button>
                <Button variant="secondary" onClick={() => setView('reader')}>
                  Switch to Reader
                </Button>
              </div>
            ) : (
              <iframe
                title={title}
                src={currentUrl}
                className="reader-mode-iframe"
                referrerPolicy="no-referrer-when-downgrade"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-popups-to-escape-sandbox"
                onError={() => setIframeFailed(true)}
              />
            )}
          </div>
        ) : (
          <article className="reader-mode-article">
            <header className="reader-mode-header">
              <h2 className="reader-mode-title">{title}</h2>
              <a className="reader-mode-url" href={currentUrl} target="_blank" rel="noreferrer">
                {currentUrl}
              </a>
              <p className="reader-mode-badge">
                Reader · extracted article text
                {extractMethod ? ` · via ${methodLabel(extractMethod)}` : ''}
                {' '}
                (click links to surf)
              </p>
            </header>
            {loading ? (
              <div className="reader-mode-loading">
                <Spinner size="lg" />
                <span>Loading full page content…</span>
              </div>
            ) : null}
            {loadError && !loading ? (
              <div className="reader-mode-error" role="alert">
                {loadError}{' '}
                <Button variant="link" isInline onClick={() => setView('website')}>
                  View website
                </Button>
                {' · '}
                <Button
                  variant="link"
                  isInline
                  onClick={() => void loadUrl(currentUrl, { replace: true, mode: 'browser' })}
                >
                  Retry with browser
                </Button>
              </div>
            ) : null}
            {summary && (
              <div
                className="reader-mode-summary knowledge-md"
                dangerouslySetInnerHTML={{ __html: markdownToHtml(summary) }}
              />
            )}
            {!loading ? (
              <div
                className="knowledge-md reader-mode-body"
                onClick={onReaderLinkClick}
                dangerouslySetInnerHTML={{ __html: markdownToHtml(body) }}
              />
            ) : null}
          </article>
        )}

        {researchPanel}
      </div>
    </div>
  )
}
