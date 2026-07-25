import { useEffect, useMemo, useState } from 'react'
import FileIcon from '@patternfly/react-icons/dist/esm/icons/file-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import { markdownToHtml } from '@/lib/chatMarkdown'
import { usePlaygroundStore } from '@/store/playgroundStore'
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
  if (n.includes('knowledge_search')) return '📚'
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

function KnowledgeCitationsBlock({ block }: { block: ChatBlock }) {
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const hits = block.knowledgeCitations?.hits || []
  return (
    <div className="tool-card knowledge-cite-card">
      <div className="tool-card-head">
        <span>📚 Knowledge sources</span>
        <span className="ok">{hits.length} cited</span>
      </div>
      {block.knowledgeCitations?.query ? (
        <div className="web-query">{block.knowledgeCitations.query}</div>
      ) : null}
      <ul className="web-results">
        {hits.map((h) => (
          <li key={`${h.canvasId}-${h.chunkId || h.text.slice(0, 24)}`}>
            <button
              type="button"
              className="msg-question-chip"
              style={{ marginBottom: 4 }}
              onClick={() => openPanelType('knowledge')}
              title="Open Knowledge panel"
            >
              {h.canvasName}
              {typeof h.score === 'number' ? ` · ${h.score.toFixed(2)}` : ''}
            </button>
            {h.sourceUrl || h.path ? (
              <div className="lc-meta" style={{ fontSize: '0.85em' }}>
                {h.path || h.sourceUrl}
              </div>
            ) : null}
            <p>{h.text.slice(0, 320)}{h.text.length > 320 ? '…' : ''}</p>
          </li>
        ))}
      </ul>
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
    case 'knowledge_citations':
      return <KnowledgeCitationsBlock block={block} />
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
                title="Allow this request once"
                onClick={() => onPermission?.(block.permission!.id, 'once')}
              >
                Allow once
              </button>
              <button
                type="button"
                className="msg-question-chip"
                title="Allow matching requests for the rest of this session"
                onClick={() => onPermission?.(block.permission!.id, 'always')}
              >
                Always allow
              </button>
              <button
                type="button"
                className="msg-question-chip"
                title="Deny this request"
                onClick={() => onPermission?.(block.permission!.id, 'reject')}
              >
                Deny
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

function isStepBlock(b: ChatBlock): boolean {
  return (
    b.type === 'tool' ||
    b.type === 'terminal' ||
    b.type === 'web_search' ||
    b.type === 'knowledge_citations'
  )
}

function isInteractiveBlock(b: ChatBlock): boolean {
  return b.type === 'question' || b.type === 'permission'
}

function isAnswerBlock(b: ChatBlock): boolean {
  return (
    b.type === 'text' ||
    b.type === 'markdown' ||
    b.type === 'image' ||
    b.type === 'attachment'
  )
}

/** Collapsible model reasoning — auto-collapses once the answer body appears. */
function ThinkingPanel({
  thinking,
  incomplete,
  hasAnswerBody,
}: {
  thinking: string
  incomplete: boolean
  hasAnswerBody: boolean
}) {
  const reasoningOnly = incomplete && !hasAnswerBody
  const [expanded, setExpanded] = useState(reasoningOnly)

  useEffect(() => {
    if (reasoningOnly) setExpanded(true)
    else if (hasAnswerBody) setExpanded(false)
  }, [reasoningOnly, hasAnswerBody])

  const approxTokens = Math.max(1, Math.ceil(thinking.length / 4))
  const label = reasoningOnly
    ? `Thinking… (~${approxTokens} tok)`
    : incomplete
      ? 'Reasoning'
      : `Thought · ~${approxTokens} tok`

  return (
    <div className={`chat-thinking${reasoningOnly ? ' chat-thinking--live' : ''}`}>
      <button
        type="button"
        className="chat-thinking-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <AngleRightIcon className={expanded ? 'chat-chevron-open' : undefined} />
        {reasoningOnly ? <span className="chat-stream-spinner" aria-hidden /> : null}
        <span>{label}</span>
        <span className="chat-thinking-hint">{expanded ? 'Hide' : 'Show'}</span>
      </button>
      {expanded ? (
        <div className="chat-thinking-body" title="Model reasoning">
          {thinking}
        </div>
      ) : null}
    </div>
  )
}

/** Collapsible tool/terminal/web/knowledge steps — collapsed when message completes. */
function StepsPanel({
  blocks,
  incomplete,
  onQuestionOption,
  onQuestionReply,
  onQuestionReject,
  onPermission,
}: {
  blocks: ChatBlock[]
  incomplete: boolean
  onQuestionOption?: (option: string) => void
  onQuestionReply?: (requestId: string, answers: string[][]) => void
  onQuestionReject?: (requestId: string) => void
  onPermission?: (permissionId: string, response: 'once' | 'always' | 'reject') => void
}) {
  const running = blocks.some(
    (b) => b.type === 'tool' && b.tool?.status === 'running',
  )
  const [expanded, setExpanded] = useState(incomplete || running)

  useEffect(() => {
    if (incomplete || running) setExpanded(true)
    else setExpanded(false)
  }, [incomplete, running])

  const n = blocks.length
  const label = incomplete || running
    ? `Running steps… (${n})`
    : `Used ${n} step${n === 1 ? '' : 's'}`

  return (
    <div className="chat-steps">
      <button
        type="button"
        className="chat-steps-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <AngleRightIcon className={expanded ? 'chat-chevron-open' : undefined} />
        {incomplete || running ? (
          <span className="chat-stream-spinner" aria-hidden />
        ) : null}
        <span>{label}</span>
        <span className="chat-thinking-hint">{expanded ? 'Hide' : 'Show'}</span>
      </button>
      {expanded ? (
        <div className="chat-steps-body">
          {blocks.map((b, i) => (
            <BlockView
              key={b.partId || `step-${i}`}
              block={b}
              onQuestionOption={onQuestionOption}
              onQuestionReply={onQuestionReply}
              onQuestionReject={onQuestionReject}
              onPermission={onPermission}
            />
          ))}
        </div>
      ) : null}
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

  const { answerBlocks, stepBlocks, interactiveBlocks } = useMemo(() => {
    const blocks = message.blocks || []
    return {
      answerBlocks: blocks.filter(isAnswerBlock),
      stepBlocks: blocks.filter(isStepBlock),
      interactiveBlocks: blocks.filter(isInteractiveBlock),
    }
  }, [message.blocks])

  const hasAnswerBody =
    !!(message.text || '').trim() ||
    answerBlocks.some(
      (b) =>
        ((b.type === 'text' || b.type === 'markdown') && !!(b.text || '').trim()) ||
        b.type === 'image' ||
        b.type === 'attachment',
    )

  const hasSteps =
    stepBlocks.length > 0 || Boolean(message.tool)

  if (message.blocks?.length) {
    return (
      <div className={`msg-blocks${incomplete ? ' msg-blocks--streaming' : ''}`}>
        {message.thinking ? (
          <ThinkingPanel
            thinking={message.thinking}
            incomplete={incomplete}
            hasAnswerBody={hasAnswerBody || hasSteps}
          />
        ) : null}

        {hasSteps ? (
          <StepsPanel
            blocks={
              message.tool && !stepBlocks.some((b) => b.type === 'tool')
                ? [
                    ...stepBlocks,
                    {
                      type: 'tool' as const,
                      tool: {
                        name: 'tool',
                        title: message.tool.title,
                        body: message.tool.body,
                        status: 'done' as const,
                      },
                    },
                  ]
                : stepBlocks
            }
            incomplete={incomplete}
            onQuestionOption={onQuestionOption}
            onQuestionReply={onQuestionReply}
            onQuestionReject={onQuestionReject}
            onPermission={onPermission}
          />
        ) : null}

        {answerBlocks.map((b, i) => (
          <BlockView
            key={b.partId || `ans-${i}`}
            block={b}
            onQuestionOption={onQuestionOption}
            onQuestionReply={onQuestionReply}
            onQuestionReject={onQuestionReject}
            onPermission={onPermission}
          />
        ))}

        {interactiveBlocks.map((b, i) => (
          <BlockView
            key={b.partId || `ix-${i}`}
            block={b}
            onQuestionOption={onQuestionOption}
            onQuestionReply={onQuestionReply}
            onQuestionReject={onQuestionReject}
            onPermission={onPermission}
          />
        ))}

        {incomplete && !hasPendingQuestion ? (
          <StreamStatus
            label={
              message.thinking && !hasAnswerBody && !hasSteps
                ? 'Thinking…'
                : hasAnswerBody || hasSteps
                  ? 'Working…'
                  : 'Generating…'
            }
          />
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
        <ThinkingPanel
          thinking={message.thinking}
          incomplete={incomplete}
          hasAnswerBody={!!(message.text || '').trim() || !!message.tool}
        />
      ) : null}
      {message.tool ? (
        <StepsPanel
          blocks={[
            {
              type: 'tool',
              tool: {
                name: 'tool',
                title: message.tool.title,
                body: message.tool.body,
                status: 'done',
              },
            },
          ]}
          incomplete={incomplete}
        />
      ) : null}
      {incomplete && !message.text && !message.thinking ? (
        <StreamStatus label="Generating…" />
      ) : null}
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
