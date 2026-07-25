/**
 * Modal loading / error gate when the OpenCode harness is not ready.
 * Greys out the chat tab and blocks interaction. Product never falls back
 * to fake/demo models for API projects.
 */

import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Spinner,
} from '@patternfly/react-core'

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
    <Modal
      variant={ModalVariant.small}
      isOpen
      // Block dismissing while connecting so users cannot "send demo" behind the gate.
      onClose={() => {
        /* no-op: require ready harness or Retry */
      }}
      aria-labelledby="chat-harness-gate-title"
      className="chat-harness-gate-modal"
      disableFocusTrap={false}
    >
      <ModalHeader title={title} labelId="chat-harness-gate-title" />
      <ModalBody>
        <div className="chat-harness-gate-body" aria-live="polite">
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
            <p className="chat-harness-gate-detail" role="alert">
              {detail}
            </p>
          ) : null}
        </div>
      </ModalBody>
      {!connecting && onRetry ? (
        <ModalFooter>
          <Button variant="primary" onClick={onRetry}>
            Retry
          </Button>
        </ModalFooter>
      ) : null}
    </Modal>
  )
}
