import { Button, Switch } from '@patternfly/react-core'
import { modeLabel } from '@/data/chatCatalog'
import { formatTokenCount } from '@/lib/chatMarkdown'
import type {
  ChatMode,
  ConversationMetrics,
  ConversationWorktree,
} from '@/types/panels'

interface ChatHeaderProps {
  title: string
  mode: ChatMode
  metrics?: ConversationMetrics
  /** Opt-in worktree isolation for this conversation */
  useWorktree?: boolean
  worktree?: ConversationWorktree
  /** False when no repo is ready — disables the toggle */
  worktreeAvailable?: boolean
  worktreeBusy?: boolean
  onUseWorktreeChange?: (enabled: boolean) => void
  onReviewWorktree?: () => void
  onApproveWorktree?: () => void
  onDiscardWorktree?: () => void
}

export function ChatHeader({
  title,
  mode,
  metrics,
  useWorktree = false,
  worktree,
  worktreeAvailable = false,
  worktreeBusy = false,
  onUseWorktreeChange,
  onReviewWorktree,
  onApproveWorktree,
  onDiscardWorktree,
}: ChatHeaderProps) {
  const used = metrics?.contextUsedTokens ?? 0
  const window = metrics?.contextWindowTokens ?? 128_000
  const pct = window > 0 ? Math.min(100, Math.round((used / window) * 100)) : 0
  const wtActive = worktree?.status === 'active'
  const toggleLocked = wtActive

  return (
    <div className="chat-header">
      <div className="chat-header-left">
        <span className="title">{title || 'Chat'}</span>
        {onUseWorktreeChange ? (
          <div className="chat-worktree-row">
            <Switch
              id="chat-use-worktree"
              label="Worktree"
              isChecked={Boolean(useWorktree || wtActive)}
              isDisabled={!worktreeAvailable || worktreeBusy || toggleLocked}
              onChange={(_e, checked) => onUseWorktreeChange(checked)}
              aria-label="Edit in isolated git worktree"
            />
            <span
              className="chat-worktree-hint"
              title="Edit in an isolated branch; approve to merge into the main checkout."
            >
              {wtActive
                ? `Isolated · ${worktree?.branch || 'ef/…'}`
                : useWorktree
                  ? 'Isolates on next Edit/Auto send'
                  : 'Optional isolation'}
            </span>
            {wtActive ? (
              <span className="chat-worktree-actions">
                <Button
                  variant="link"
                  isInline
                  isDisabled={worktreeBusy}
                  onClick={onReviewWorktree}
                >
                  Review
                </Button>
                <Button
                  variant="link"
                  isInline
                  isDisabled={worktreeBusy}
                  onClick={onApproveWorktree}
                >
                  Approve
                </Button>
                <Button
                  variant="link"
                  isInline
                  isDanger
                  isDisabled={worktreeBusy}
                  onClick={onDiscardWorktree}
                >
                  Discard
                </Button>
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="chat-metrics" aria-label="Conversation metrics">
        <span className="metric" title={`Context ${used.toLocaleString()} / ${window.toLocaleString()} tokens`}>
          <span className="metric-label">Context</span>
          <span className="metric-value">
            {formatTokenCount(used)}/{formatTokenCount(window)}
          </span>
          <span className="metric-bar" aria-hidden>
            <span className="metric-bar-fill" style={{ width: `${pct}%` }} />
          </span>
        </span>
        <span className="metric" title="Tokens per second (last response)">
          <span className="metric-label">tok/s</span>
          <span className="metric-value">
            {metrics?.tokensPerSec != null && metrics.tokensPerSec > 0
              ? metrics.tokensPerSec
              : '—'}
          </span>
        </span>
        <span className="metric" title="Time to first token">
          <span className="metric-label">TTFT</span>
          <span className="metric-value">
            {metrics?.ttftMs != null && metrics.ttftMs > 0
              ? `${metrics.ttftMs}ms`
              : '—'}
          </span>
        </span>
        <span
          className="metric metric-mode-mobile"
          title="Permission mode (change in composer)"
        >
          <span className="metric-label">Mode</span>
          <span className="metric-value">{modeLabel(mode)}</span>
        </span>
      </div>
    </div>
  )
}
