/**
 * Full-panel splash when the OpenCode harness cannot be started or reached.
 * Product never falls back to fake/demo models in this state.
 */

interface ChatHarnessUnavailableProps {
  /** Technical detail from ensure / proxy (optional). */
  detail?: string | null
  /** True while bootstrap is in progress. */
  connecting?: boolean
  onRetry?: () => void
}

export function ChatHarnessUnavailable({
  detail,
  connecting,
  onRetry,
}: ChatHarnessUnavailableProps) {
  if (connecting) {
    return (
      <div className="chat-empty chat-harness-splash" role="status" aria-live="polite">
        <h2 className="chat-empty-title">Starting chat harness…</h2>
        <p className="chat-empty-desc">
          Connecting to OpenCode in this project’s sandbox. This is not a demo catalog —
          chat waits for the real harness.
        </p>
      </div>
    )
  }

  return (
    <div className="chat-empty chat-harness-splash" role="alert">
      <h2 className="chat-empty-title">Background chat isn’t available</h2>
      <p className="chat-empty-desc">
        The OpenCode harness for this project sandbox could not be started or reached. Chat
        needs a healthy harness — Everflow does not fall back to fake or demo models.
      </p>
      {detail ? (
        <p
          className="chat-empty-desc"
          style={{ opacity: 0.85, fontSize: '0.9em', marginTop: 8, maxWidth: 520 }}
        >
          {detail}
        </p>
      ) : null}
      {onRetry ? (
        <button type="button" className="chat-empty-chip" onClick={onRetry} style={{ marginTop: 16 }}>
          Retry
        </button>
      ) : null}
    </div>
  )
}
