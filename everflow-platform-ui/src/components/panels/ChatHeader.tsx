import {
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import { CHAT_MODES, modeLabel } from '@/data/chatCatalog'
import { formatTokenCount } from '@/lib/chatMarkdown'
import type { ChatMode, ConversationMetrics } from '@/types/panels'

interface ChatHeaderProps {
  title: string
  mode: ChatMode
  metrics?: ConversationMetrics
  agents?: { name: string; role: string }[]
  onModeChange: (mode: ChatMode) => void
}

export function ChatHeader({
  title,
  mode,
  metrics,
  agents,
  onModeChange,
}: ChatHeaderProps) {
  const used = metrics?.contextUsedTokens ?? 0
  const window = metrics?.contextWindowTokens ?? 128_000
  const pct = window > 0 ? Math.min(100, Math.round((used / window) * 100)) : 0

  return (
    <div className="chat-header">
      <div className="chat-header-left">
        <span className="title">{title || 'Chat'}</span>
        {agents && agents.length > 0 ? (
          <div className="chat-header-agents" title="Agents in this chat">
            {agents.map((a) => (
              <span key={a.name} className={`agent-chip agent-${a.role}`}>
                {a.name}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <ToggleGroup className="chat-mode-toggle" aria-label="Chat mode">
        {CHAT_MODES.map((m) => (
          <ToggleGroupItem
            key={m.id}
            text={m.label}
            buttonId={`chat-mode-${m.id}`}
            isSelected={mode === m.id}
            onChange={() => onModeChange(m.id)}
            title={m.description}
          />
        ))}
      </ToggleGroup>

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
          <span className="metric-value">{metrics?.tokensPerSec ?? '—'}</span>
        </span>
        <span className="metric" title="Time to first token">
          <span className="metric-label">TTFT</span>
          <span className="metric-value">
            {metrics?.ttftMs != null ? `${metrics.ttftMs}ms` : '—'}
          </span>
        </span>
        <span className="metric metric-mode-mobile" title="Mode">
          <span className="metric-label">Mode</span>
          <span className="metric-value">{modeLabel(mode)}</span>
        </span>
      </div>
    </div>
  )
}
