import { useState } from 'react'
import { Button } from '@patternfly/react-core'
import CopyIcon from '@patternfly/react-icons/dist/esm/icons/copy-icon'
import EditIcon from '@patternfly/react-icons/dist/esm/icons/edit-icon'
import RedoIcon from '@patternfly/react-icons/dist/esm/icons/redo-icon'
import CodeBranchIcon from '@patternfly/react-icons/dist/esm/icons/code-branch-icon'
import CheckIcon from '@patternfly/react-icons/dist/esm/icons/check-icon'
import { messageToMarkdown, messageToRaw } from '@/lib/chatMarkdown'
import type { ChatMessage } from '@/types/panels'
import { ChatMessageContent } from './ChatMessageContent'

interface ChatMessageRowProps {
  message: ChatMessage
  onEdit?: (messageId: string, text: string) => void
  onRetry?: (messageId: string) => void
  onFork?: (messageId: string) => void
  onQuestionOption?: (option: string) => void
  onQuestionReply?: (requestId: string, answers: string[][]) => void
  onQuestionReject?: (requestId: string) => void
  onPermission?: (permissionId: string, response: 'once' | 'always' | 'reject') => void
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function agentInitials(name?: string): string {
  if (!name) return 'AI'
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function ChatMessageRow({
  message,
  onEdit,
  onRetry,
  onFork,
  onQuestionOption,
  onQuestionReply,
  onQuestionReject,
  onPermission,
}: ChatMessageRowProps) {
  const isUser = message.role === 'user'
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(message.text || '')
  const [copied, setCopied] = useState<'md' | 'raw' | null>(null)

  const flashCopied = (kind: 'md' | 'raw') => {
    setCopied(kind)
    window.setTimeout(() => setCopied(null), 1200)
  }

  const avatarLabel = isUser ? 'U' : agentInitials(message.agent?.name)
  const agentRole = message.agent?.role || 'general'

  return (
    <div className={`msg ${isUser ? 'user' : 'assistant'}${editing ? ' is-editing' : ''}`}>
      <div
        className={`msg-avatar${isUser ? '' : ` agent-${agentRole}`}`}
        title={message.agent?.name || (isUser ? 'You' : 'Assistant')}
      >
        {avatarLabel}
      </div>
      <div className="msg-col">
        {!isUser && message.agent ? (
          <div className={`msg-agent-label agent-${agentRole}`}>{message.agent.name}</div>
        ) : null}
        <div className="bubble">
          {editing ? (
            <div className="msg-edit">
              <textarea
                className="msg-edit-input"
                value={draft}
                rows={3}
                onChange={(e) => setDraft(e.target.value)}
                aria-label="Edit message"
              />
              <div className="msg-edit-actions">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    const t = draft.trim()
                    if (!t) return
                    onEdit?.(message.id, t)
                    setEditing(false)
                  }}
                >
                  Save & re-run
                </Button>
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => {
                    setDraft(message.text || '')
                    setEditing(false)
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <ChatMessageContent
              message={message}
              onQuestionOption={onQuestionOption}
              onQuestionReply={onQuestionReply}
              onQuestionReject={onQuestionReject}
              onPermission={onPermission}
            />
          )}
        </div>
        <div className="msg-actions">
          {isUser ? (
            <>
              <button
                type="button"
                className="msg-action-btn"
                title="Modify request"
                onClick={() => {
                  setDraft(message.text || message.blocks?.find((b) => b.text)?.text || '')
                  setEditing(true)
                }}
              >
                <EditIcon /> <span>Modify</span>
              </button>
              <button
                type="button"
                className="msg-action-btn"
                title="Fork conversation from here"
                onClick={() => onFork?.(message.id)}
              >
                <CodeBranchIcon /> <span>Fork</span>
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="msg-action-btn"
                title="Copy as Markdown"
                onClick={async () => {
                  if (await copyText(messageToMarkdown(message))) flashCopied('md')
                }}
              >
                {copied === 'md' ? <CheckIcon /> : <CopyIcon />}{' '}
                <span>{copied === 'md' ? 'Copied' : 'Copy MD'}</span>
              </button>
              <button
                type="button"
                className="msg-action-btn"
                title="Copy raw text"
                onClick={async () => {
                  if (await copyText(messageToRaw(message))) flashCopied('raw')
                }}
              >
                {copied === 'raw' ? <CheckIcon /> : <CopyIcon />}{' '}
                <span>{copied === 'raw' ? 'Copied' : 'Copy raw'}</span>
              </button>
              <button
                type="button"
                className="msg-action-btn"
                title="Retry response"
                onClick={() => onRetry?.(message.id)}
              >
                <RedoIcon /> <span>Retry</span>
              </button>
              <button
                type="button"
                className="msg-action-btn"
                title="Fork conversation from here"
                onClick={() => onFork?.(message.id)}
              >
                <CodeBranchIcon /> <span>Fork</span>
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
