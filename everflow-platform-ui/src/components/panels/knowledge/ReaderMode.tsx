import { Button, TextInput } from '@patternfly/react-core'
import { useState } from 'react'
import { markdownToHtml } from '@/lib/chatMarkdown'
import type { WebSearchHit } from '@/types/studio'
import { researchReply, summarizeReader } from './demoKnowledge'

interface ReaderModeProps {
  hit: WebSearchHit
  onBack: () => void
  onAddToKnowledge: (hit: WebSearchHit) => void
}

interface ChatLine {
  role: 'user' | 'assistant'
  text: string
}

export function ReaderMode({ hit, onBack, onAddToKnowledge }: ReaderModeProps) {
  const body = hit.readerMarkdown || `# ${hit.title}\n\n${hit.snippet}\n\n_No full reader text for this result._`
  const [summary, setSummary] = useState<string | null>(null)
  const [researchOpen, setResearchOpen] = useState(false)
  const [chat, setChat] = useState<ChatLine[]>([])
  const [draft, setDraft] = useState('')

  const sendResearch = () => {
    const text = draft.trim()
    if (!text) return
    const reply = researchReply(text, hit.title)
    setChat((c) => [...c, { role: 'user', text }, { role: 'assistant', text: reply }])
    setDraft('')
  }

  return (
    <div className="reader-mode">
      <div className="reader-mode-toolbar">
        <Button variant="link" isInline onClick={onBack}>
          ← Back to results
        </Button>
        <div className="reader-mode-actions">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setSummary(summarizeReader(hit.title, body))}
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
          <Button size="sm" variant="primary" onClick={() => onAddToKnowledge(hit)}>
            Add to knowledge
          </Button>
        </div>
      </div>

      <article className="reader-mode-article">
        <header className="reader-mode-header">
          <h2 className="reader-mode-title">{hit.title}</h2>
          <a className="reader-mode-url" href={hit.url} target="_blank" rel="noreferrer">
            {hit.url}
          </a>
          <p className="reader-mode-badge">Reader mode · clean text only</p>
        </header>
        {summary && (
          <div
            className="reader-mode-summary knowledge-md"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(summary) }}
          />
        )}
        <div
          className="knowledge-md reader-mode-body"
          dangerouslySetInnerHTML={{ __html: markdownToHtml(body) }}
        />
      </article>

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
