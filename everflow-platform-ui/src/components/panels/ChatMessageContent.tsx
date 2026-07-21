import FileIcon from '@patternfly/react-icons/dist/esm/icons/file-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import { markdownToHtml } from '@/lib/chatMarkdown'
import type { ChatBlock, ChatMessage } from '@/types/panels'

interface ChatMessageContentProps {
  message: ChatMessage
  onQuestionOption?: (option: string) => void
  onPermission?: (permissionId: string, response: 'once' | 'always' | 'reject') => void
}

function BlockView({
  block,
  onQuestionOption,
  onPermission,
}: {
  block: ChatBlock
  onQuestionOption?: (option: string) => void
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
        <div className="msg-question">
          <p className="msg-question-prompt">{block.text}</p>
          <div className="msg-question-options">
            {(block.options || []).map((opt) => (
              <button
                key={opt}
                type="button"
                className="msg-question-chip"
                onClick={() => onQuestionOption?.(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
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
              {block.terminal?.exitCode ? `exit ${block.terminal.exitCode}` : '✓ done'}
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
        <div className="tool-card">
          <div className="tool-card-head">
            <span>🛠 {block.tool?.title}</span>
            <span className="ok">
              {block.tool?.status === 'running'
                ? '…'
                : block.tool?.status === 'error'
                  ? 'error'
                  : '✓ done'}
            </span>
          </div>
          <pre>{block.tool?.body}</pre>
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

export function ChatMessageContent({
  message,
  onQuestionOption,
  onPermission,
}: ChatMessageContentProps) {
  if (message.blocks?.length) {
    return (
      <div className="msg-blocks">
        {message.thinking ? <div className="thinking">{message.thinking}</div> : null}
        {message.blocks.map((b, i) => (
          <BlockView
            key={i}
            block={b}
            onQuestionOption={onQuestionOption}
            onPermission={onPermission}
          />
        ))}
      </div>
    )
  }

  return (
    <>
      {message.thinking ? <div className="thinking">{message.thinking}</div> : null}
      {message.tool ? (
        <div className="tool-card">
          <div className="tool-card-head">
            <span>🛠 {message.tool.title}</span>
            <span className="ok">✓ done</span>
          </div>
          <pre>{message.tool.body}</pre>
        </div>
      ) : null}
      {message.text ? (
        <div
          className="msg-md"
          dangerouslySetInnerHTML={{
            __html: markdownToHtml(message.text),
          }}
        />
      ) : null}
    </>
  )
}
