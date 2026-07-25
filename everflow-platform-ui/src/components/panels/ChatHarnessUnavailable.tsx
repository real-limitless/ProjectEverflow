/**
 * Chat-tab-only loading / error gate when the OpenCode harness is not ready.
 * Covers only the chat panel (not the full playground). Product never falls
 * back to fake/demo models for API projects.
 */

import { Button, Spinner } from '@patternfly/react-core'

interface ChatHarnessGateProps {
  isOpen: boolean
  /** Technical detail from ensure / proxy (optional). */
  detail?: string | null
  /** True while bootstrap is in progress. */
  connecting?: boolean
  onRetry?: () => void
}

export function ChatHarnessUnavailable({
  isOpen,
  detail,
  connecting,
  onRetry,
}: ChatHarnessGateProps) {
  if (!isOpen) return null

  const title = connecting
    ? 'Starting chat harness…'
    : 'Background chat isn’t available'

  return (
    <div
      className="chat-harness-gate-overlay"
      role={connecting ? 'status' : 'alert'}
      aria-live="polite"
      aria-labelledby="chat-harness-gate-title"
    >
      <div className="chat-harness-gate-card">
        <h2 id="chat-harness-gate-title" className="chat-harness-gate-title">
          {title}
        </h2>
        {connecting ? (
          <div className="chat-harness-gate-spinner">
            <Spinner size="lg" aria-label="Starting OpenCode harness" />
          </div>
        ) : null}
        <p className="chat-harness-gate-desc">
          {connecting
            ? 'Connecting to OpenCode in this project’s sandbox. Chat is blocked until the real harness is healthy — Everflow does not use demo replies for API projects.'
            : 'The OpenCode harness for this project sandbox could not be started or reached. Chat needs a healthy harness — Everflow does not fall back to fake or demo models.'}
        </p>
        {!connecting && detail ? (
          <p className="chat-harness-gate-detail">{detail}</p>
        ) : null}
        {!connecting && onRetry ? (
          <div className="chat-harness-gate-actions">
            <Button variant="primary" onClick={onRetry}>
              Retry
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
