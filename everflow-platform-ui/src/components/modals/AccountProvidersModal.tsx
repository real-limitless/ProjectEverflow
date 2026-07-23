import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
} from '@patternfly/react-core'
import { ProvidersManager } from '@/components/providers/ProvidersManager'

interface AccountProvidersModalProps {
  isOpen: boolean
  onClose: () => void
}

export function AccountProvidersModal({ isOpen, onClose }: AccountProvidersModalProps) {
  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={onClose}
      aria-labelledby="account-providers-title"
      className="project-settings-modal"
    >
      <ModalHeader title="AI providers" labelId="account-providers-title" />
      <ModalBody>
        <ProvidersManager
          scope="user"
          lead={
            <>
              Connect OpenRouter, OpenAI, Anthropic, or xAI with your own API keys. Account keys are
              used by default for chat, embeddings, and OCR. Project settings can override them for
              a single project.
            </>
          }
        />
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </ModalFooter>
    </Modal>
  )
}
