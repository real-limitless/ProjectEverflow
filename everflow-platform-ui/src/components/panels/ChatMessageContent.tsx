import { useState } from 'react'
import FileIcon from '@patternfly/react-icons/dist/esm/icons/file-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import { markdownToHtml } from '@/lib/chatMarkdown'
import type {
  ChatBlock,
  ChatMessage,
  ChatQuestionItem,
  ChatQuestionRequest,
} from '@/types/panels'

interface ChatMessageContentProps {
  message: ChatMessage
  /** Legacy: single option string (demo / part-shaped questions without request id) */
  onQuestionOption?: (option: string) => void
  /** OpenCode question reply: requestId + answers (one string[] per question) */
  onQuestionReply?: (requestId: string, answers: string[][]) => void
  onQuestionReject?: (requestId: string) => void
  onPermission?: (permissionId: string, response: 'once' | 'always' | 'reject') => void
}

function toolIcon(name?: string): string {
  const n = (name || '').toLowerCase()
  if (n === 'bash' || n === 'shell') return '⌘'
  if (n === 'read') return '📖'
  if (n === 'write' || n === 'edit' || n === 'apply_patch') return '✏️'
  if (n === 'grep' || n === 'glob') return '🔎'
  if (n === 'webfetch' || n === 'websearch' || n === 'web_search') return '🌐'
  if (n === 'todowrite' || n === 'todoread') return '☑'
  if (n === 'skill') return '🧩'
  if (n === 'question') return '❓'
  return '🛠'
}

function QuestionBlockView({
  block,
  onQuestionOption,
  onQuestionReply,
  onQuestionReject,
}: {
  block: ChatBlock
  onQuestionOption?: (option: string) => void
  onQuestionReply?: (requestId: string, answers: string[][]) => void
  onQuestionReject?: (requestId: string) => void
}) {
  const qr: ChatQuestionRequest | undefined = block.questionRequest
  const resolved = qr?.status === 'answered' || qr?.status === 'rejected'
  const items: ChatQuestionItem[] =
    qr?.items?.length
      ? qr.items
      : [
          {
            question: block.text || 'Choose an option',
            options: (block.options || []).map((label) => ({ label })),
            custom: true,
          },
        ]

  const [selected, setSelected] = useState<string[][]>(() =>
    items.map(() => [] as string[]),
  )
  const [customText, setCustomText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const multi = items.length > 1 || items.some((i) => i.multiple)
  const locked = resolved || submitting

  const sendReply = (answers: string[][]) => {
    if (locked) return
    setSubmitting(true)
    if (qr?.id && onQuestionReply) {
      onQuestionReply(qr.id, answers)
      return
    }
    // Demo / no request id → send first choice as a chat message
    const label = answers.flat().filter(Boolean)[0]
    if (label) onQuestionOption?.(label)
    setSubmitting(false)
  }

  const pick = (qi: number, label: string, multiple?: boolean) => {
    if (locked) return
    // Single-question single-select → reply immediately
    if (!multi && !items[0]?.multiple) {
      sendReply([[label]])
      return
    }
    setSelected((prev) => {
      const next = prev.map((row) => [...row])
      if (multiple) {
        const set = new Set(next[qi] || [])
        if (set.has(label)) set.delete(label)
        else set.add(label)
        next[qi] = Array.from(set)
      } else {
        next[qi] = [label]
      }
      return next
    })
  }

  const submit = () => {
    if (locked || !qr?.id) return
    const answers = selected.map((row, i) => {
      if (row.length) return row
      // custom free-text for last empty slot
      if (customText.trim() && i === items.length - 1) return [customText.trim()]
      return row
    })
    if (answers.every((a) => a.length === 0) && customText.trim()) {
      sendReply(items.map((_, i) => (i === 0 ? [customText.trim()] : [])))
      return
    }
    if (answers.some((a) => a.length === 0)) return
    sendReply(answers)
  }

  const submitCustom = () => {
    const t = customText.trim()
    if (!t || locked) return
    if (qr?.id) {
      sendReply(
        items.map((_, i) => (i === 0 ? [t] : selected[i]?.length ? selected[i] : [])),
      )
    } else {
      onQuestionOption?.(t)
    }
  }

  return (
    <div
      className={`msg-question${resolved ? ' msg-question--resolved' : ''}${submitting && !resolved ? ' msg-question--submitting' : ''}`}
    >
      {items.map((item, qi) => (
        <div key={qi} className="msg-question-item">
          {item.header ? (
            <div className="msg-question-header">{item.header}</div>
          ) : null}
          <p className="msg-question-prompt">{item.question}</p>
          <div className="msg-question-options">
            {item.options.map((opt) => {
              const active = (selected[qi] || []).includes(opt.label)
              return (
                <button
                  key={opt.label}
                  type="button"
                  className={`msg-question-chip${active ? ' is-selected' : ''}`}
                  disabled={locked}
                  title={opt.description || opt.label}
                  onClick={() => pick(qi, opt.label, item.multiple)}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}

      {!locked && (items.some((i) => i.custom !== false) || !qr) ? (
        <div className="msg-question-custom">
          <input
            type="text"
            className="msg-question-custom-input"
            placeholder="Or type your own answer…"
            value={customText}
            disabled={locked}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                if (multi) submit()
                else submitCustom()
              }
            }}
          />
          {!multi ? (
            <button
              type="button"
              className="msg-question-chip"
              disabled={!customText.trim() || locked}
              onClick={submitCustom}
            >
              Send
            </button>
          ) : null}
        </div>
      ) : null}

      {!locked && multi && qr?.id ? (
        <div className="msg-question-actions">
          <button
            type="button"
            className="msg-question-chip msg-question-chip--primary"
            onClick={submit}
          >
            Submit answers
          </button>
          {onQuestionReject ? (
            <button
              type="button"
              className="msg-question-chip"
              onClick={() => onQuestionReject(qr.id)}
            >
              Skip
            </button>
          ) : null}
        </div>
      ) : null}

      {submitting && !resolved ? (
        <div className="msg-question-status" role="status">
          Submitting answer…
        </div>
      ) : null}

      {resolved ? (
        <div className="msg-question-status">
          {qr?.status === 'rejected' ? 'Skipped' : 'Answered'}
        </div>
      ) : null}
    </div>
  )
}

function BlockView({
  block,
  onQuestionOption,
  onQuestionReply,
  onQuestionReject,
  onPermission,
}: {
  block: ChatBlock
  onQuestionOption?: (option: string) => void
  onQuestionReply?: (requestId: string, answers: string[][]) => void
  onQuestionReject?: (requestId: string) => void
  onPermission?: (permissionId: string, response: 'once' | 'always' | 'reject') => void
}) {
  switch (block.type) {
    case 'markdown':
      return (
        <div
          className="msg-md"
          dangerouslySetInnerHTML={{ __html: markdownToHtml(block.text || '') }}
        />
      )
    case 'text':
      return <p className="msg-text">{block.text}</p>
    case 'question':
      return (
        <QuestionBlockView
          block={block}
          onQuestionOption={onQuestionOption}
          onQuestionReply={onQuestionReply}
          onQuestionReject={onQuestionReject}
        />
      )
    case 'image':
      return (
        <figure className="msg-image">
          <a href={block.imageUrl} target="_blank" rel="noreferrer">
            <img src={block.imageUrl} alt={block.alt || 'Attachment'} />
          </a>
          {block.alt ? <figcaption>{block.alt}</figcaption> : null}
        </figure>
      )
    case 'attachment':
      return (
        <div className="msg-attachment">
          <FileIcon />
          <div className="msg-attachment-meta">
            <span className="msg-attachment-name">{block.attachment?.name}</span>
            <span className="msg-attachment-size">
              {block.attachment?.sizeLabel} · {block.attachment?.mime}
            </span>
          </div>
        </div>
      )
    case 'terminal':
      return (
        <div className="tool-card term-card">
          <div className="tool-card-head">
            <span>⌘ Terminal</span>
            <span className={block.terminal?.exitCode ? 'err' : 'ok'}>
              {block.terminal?.exitCode
                ? `exit ${block.terminal.exitCode}`
                : block.terminal?.output === '…'
                  ? '…'
                  : '✓ done'}
            </span>
          </div>
          <pre>
            <span className="term-cmd">$ {block.terminal?.command}</span>
            {'\n'}
            {block.terminal?.output}
          </pre>
        </div>
      )
    case 'web_search':
      return (
        <div className="tool-card web-card">
          <div className="tool-card-head">
            <span>🔍 Web search</span>
            <span className="ok">✓ done</span>
          </div>
          <div className="web-query">{block.webSearch?.query}</div>
          <ul className="web-results">
            {(block.webSearch?.results || []).map((r) => (
              <li key={r.url}>
                <a href={r.url} target="_blank" rel="noreferrer">
                  {r.title} <ExternalLinkAltIcon />
                </a>
                <p>{r.snippet}</p>
              </li>
            ))}
          </ul>
        </div>
      )
    case 'tool':
      return (
        <div className={`tool-card tool-card--${block.tool?.status || 'done'}`}>
          <div className="tool-card-head">
            <span>
              {toolIcon(block.tool?.name)} {block.tool?.title}
            </span>
            <span
              className={
                block.tool?.status === 'error'
                  ? 'err'
                  : block.tool?.status === 'running'
                    ? ''
                    : 'ok'
              }
            >
              {block.tool?.status === 'running'
                ? '… running'
                : block.tool?.status === 'error'
                  ? 'error'
                  : '✓ done'}
            </span>
          </div>
          {block.tool?.body ? <pre>{block.tool.body}</pre> : null}
        </div>
      )
    case 'permission':
      return (
        <div className="tool-card permission-card">
          <div className="tool-card-head">
            <span>🔐 {block.permission?.title || 'Permission'}</span>
            <span className={block.permission?.status === 'resolved' ? 'ok' : ''}>
              {block.permission?.status === 'resolved' ? 'resolved' : 'needs approval'}
            </span>
          </div>
          {block.permission?.detail ? <pre>{block.permission.detail}</pre> : null}
          {block.permission?.status !== 'resolved' && block.permission?.id ? (
            <div className="msg-question-options" style={{ marginTop: 8 }}>
              <button
                type="button"
                className="msg-question-chip"
                onClick={() => onPermission?.(block.permission!.id, 'once')}
              >
                Once
              </button>
              <button
                type="button"
                className="msg-question-chip"
                onClick={() => onPermission?.(block.permission!.id, 'always')}
              >
                Always
              </button>
              <button
                type="button"
                className="msg-question-chip"
                onClick={() => onPermission?.(block.permission!.id, 'reject')}
              >
                Reject
              </button>
            </div>
          ) : null}
        </div>
      )
    default:
      return block.text ? <p className="msg-text">{block.text}</p> : null
  }
}

function StreamStatus({ label }: { label: string }) {
  return (
    <div className="chat-stream-status" role="status" aria-live="polite">
      <span className="chat-stream-spinner" aria-hidden />
      <span>{label}</span>
    </div>
  )
}

export function ChatMessageContent({
  message,
  onQuestionOption,
  onQuestionReply,
  onQuestionReject,
  onPermission,
}: ChatMessageContentProps) {
  const incomplete =
    message.role === 'assistant' &&
    (message.generationStatus === 'incomplete' || message.id.startsWith('pending-'))
  const hasPendingQuestion = (message.blocks || []).some(
    (b) =>
      b.type === 'question' &&
      (!b.questionRequest || b.questionRequest.status === 'pending'),
  )
  const hasBody =
    !!(message.text || '').trim() ||
    (message.blocks || []).some(
      (b) =>
        (b.type === 'text' || b.type === 'markdown') && !!(b.text || '').trim(),
    ) ||
    !!(
      message.tool ||
      message.blocks?.some(
        (b) =>
          b.type === 'tool' ||
          b.type === 'terminal' ||
          b.type === 'web_search' ||
          b.type === 'question' ||
          b.type === 'permission',
      )
    )

  if (message.blocks?.length) {
    return (
      <div className={`msg-blocks${incomplete ? ' msg-blocks--streaming' : ''}`}>
        {message.thinking ? (
          <div className="thinking" title="Model reasoning">
            {message.thinking}
          </div>
        ) : null}
        {message.blocks.map((b, i) => (
          <BlockView
            key={b.partId || i}
            block={b}
            onQuestionOption={onQuestionOption}
            onQuestionReply={onQuestionReply}
            onQuestionReject={onQuestionReject}
            onPermission={onPermission}
          />
        ))}
        {incomplete && !hasPendingQuestion ? (
          <StreamStatus label={hasBody ? 'Working…' : 'Generating…'} />
        ) : null}
        {hasPendingQuestion && incomplete ? (
          <StreamStatus label="Waiting for your answer…" />
        ) : null}
      </div>
    )
  }

  return (
    <>
      {message.thinking ? (
        <div className="thinking" title="Model reasoning">
          {message.thinking}
        </div>
      ) : null}
      {message.tool ? (
        <div className="tool-card">
          <div className="tool-card-head">
            <span>
              {toolIcon()} {message.tool.title}
            </span>
            <span className="ok">✓ done</span>
          </div>
          <pre>{message.tool.body}</pre>
        </div>
      ) : null}
      {incomplete && !message.text ? <StreamStatus label="Generating…" /> : null}
      {message.text ? (
        <div
          className={`msg-md${incomplete ? ' msg-md--streaming' : ''}`}
          dangerouslySetInnerHTML={{
            __html: markdownToHtml(message.text),
          }}
        />
      ) : null}
      {incomplete && message.text ? <StreamStatus label="Streaming…" /> : null}
    </>
  )
}
