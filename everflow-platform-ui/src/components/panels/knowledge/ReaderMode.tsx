import {
  Button,
  Spinner,
  TextInput,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { useEffect, useState } from 'react'
import { ApiError, fetchKnowledgeWebRead } from '@/lib/api'
import { markdownToHtml } from '@/lib/chatMarkdown'
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
  const [markdown, setMarkdown] = useState(
    hit.readerMarkdown || '',
  )
  const [title, setTitle] = useState(hit.title)
  const [loading, setLoading] = useState(!hit.readerMarkdown)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [researchOpen, setResearchOpen] = useState(false)
  const [chat, setChat] = useState<ChatLine[]>([])
  const [draft, setDraft] = useState('')
  const [iframeFailed, setIframeFailed] = useState(false)

  useEffect(() => {
    setTitle(hit.title)
    setSummary(null)
    setChat([])
    setDraft('')
    setIframeFailed(false)
    setView('reader')

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
        // Fallback so the reader isn't empty
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
  }, [hit.id, hit.url, hit.title, hit.snippet, hit.readerMarkdown, projectId, onContentLoaded])

  const body =
    markdown ||
    `# ${title}\n\n${hit.snippet}\n\n_No full reader text for this result._`

  const sendResearch = () => {
    const text = draft.trim()
    if (!text) return
    const reply = researchReply(text, title)
    setChat((c) => [...c, { role: 'user', text }, { role: 'assistant', text: reply }])
    setDraft('')
  }

  const enrichedHit: WebSearchHit = {
    ...hit,
    title,
    readerMarkdown: markdown || hit.readerMarkdown,
  }

  return (
    <div className="reader-mode">
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
            isDisabled={loading || !markdown}
            onClick={() => setSummary(summarizeReader(title, body))}
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
            Live site · some sites block embedding; switch to Reader for extracted text
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

      {researchOpen && (
        <div className="research-chat">
          <div className="research-chat-head">
            Ephemeral research chat · not saved to main chatbot
          </div>
          <div className="research-chat-log">
            {chat.length === 0 ? (
              <p className="lc-meta">
                Ask to summarize, extract steps, or draft notes from this page. Pin to knowledge
                when you want it available to the main assistant.
              </p>
            ) : (
              chat.map((line, i) => (
                <div
                  key={`${line.role}-${i}`}
                  className={`research-chat-line is-${line.role}`}
                >
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
          </div>
          <div className="research-chat-compose">
            <TextInput
              value={draft}
              onChange={(_e, v) => setDraft(v)}
              placeholder="Ask about this article…"
              aria-label="Research chat message"
              onKeyDown={(e) => {
                if (e.key === 'Enter') sendResearch()
              }}
            />
            <Button variant="primary" onClick={sendResearch} isDisabled={!draft.trim()}>
              Send
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
