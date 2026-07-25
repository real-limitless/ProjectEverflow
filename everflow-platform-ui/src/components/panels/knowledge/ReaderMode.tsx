import {
  Button,
  Spinner,
  TextInput,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { useEffect, useRef, useState } from 'react'
import { getProject } from '@/data/projects'
import {
  ApiError,
  fetchKnowledgeWebRead,
  isDemoMode,
  promoteResearchToCanvas,
} from '@/lib/api'
import { markdownToHtml } from '@/lib/chatMarkdown'
import {
  endResearchSession,
  researchChatTurn,
  startResearchSession,
  summarizeArticleWithOpenCode,
} from '@/lib/knowledge/researchChat'
import { pushToast } from '@/lib/studioToast'
import type { WebSearchHit } from '@/types/studio'
import { researchReply, summarizeReader } from './demoKnowledge'

interface ReaderModeProps {
  hit: WebSearchHit
  projectId: string
  onBack: () => void
  onAddToKnowledge: (hit: WebSearchHit) => void
  /** Persist extracted markdown onto the hit in the parent list */
  onContentLoaded?: (hitId: string, markdown: string, title?: string) => void
}

interface ChatLine {
  role: 'user' | 'assistant'
  text: string
}

type ViewMode = 'reader' | 'website'

export function ReaderMode({
  hit,
  projectId,
  onBack,
  onAddToKnowledge,
  onContentLoaded,
}: ReaderModeProps) {
  const [view, setView] = useState<ViewMode>('reader')
  const [markdown, setMarkdown] = useState(hit.readerMarkdown || '')
  const [title, setTitle] = useState(hit.title)
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
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  useEffect(() => {
    setTitle(hit.title)
    setSummary(null)
    setChat([])
    setDraft('')
    setIframeFailed(false)
    setView('reader')
    const prevSession = researchSessionRef.current
    researchSessionRef.current = null
    if (prevSession && useApi) {
      void endResearchSession(projectId, prevSession)
    }

    if (hit.readerMarkdown) {
      setMarkdown(hit.readerMarkdown)
      setLoading(false)
      setLoadError(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setLoadError(null)
    setMarkdown('')

    void (async () => {
      try {
        const result = await fetchKnowledgeWebRead(projectId, hit.url)
        if (cancelled) return
        setMarkdown(result.markdown)
        if (result.title) setTitle(result.title)
        onContentLoaded?.(hit.id, result.markdown, result.title)
      } catch (e) {
        if (cancelled) return
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : 'Failed to load page content'
        setLoadError(msg)
        setMarkdown(
          `# ${hit.title}\n\n${hit.snippet}\n\n_Could not extract full page text._\n\n[Open original](${hit.url})\n`,
        )
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [hit.id, hit.url, hit.title, hit.snippet, hit.readerMarkdown, projectId, onContentLoaded, useApi])

  useEffect(() => {
    return () => {
      const sid = researchSessionRef.current
      if (sid && useApi) void endResearchSession(projectId, sid)
    }
  }, [projectId, useApi])

  const body =
    markdown ||
    `# ${title}\n\n${hit.snippet}\n\n_No full reader text for this result._`

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
      // Fallback demo summary if OpenCode unavailable
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
    readerMarkdown: markdown || hit.readerMarkdown,
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
        source_url: hit.url,
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

      <div className="reader-mode-main">
        {view === 'website' ? (
          <div className="reader-mode-website">
            <div className="reader-mode-website-bar">
              <a className="reader-mode-url" href={hit.url} target="_blank" rel="noreferrer">
                {hit.url}
              </a>
              <Button
                size="sm"
                variant="link"
                isInline
                onClick={() => window.open(hit.url, '_blank', 'noopener,noreferrer')}
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
                  onClick={() => window.open(hit.url, '_blank', 'noopener,noreferrer')}
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
                src={hit.url}
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
              <a className="reader-mode-url" href={hit.url} target="_blank" rel="noreferrer">
                {hit.url}
              </a>
              <p className="reader-mode-badge">
                Reader · extracted article text (ads/chrome removed)
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
