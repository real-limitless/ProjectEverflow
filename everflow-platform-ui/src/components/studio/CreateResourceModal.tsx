import { Button, Form, Modal, ModalBody, ModalFooter, ModalHeader, ModalVariant } from '@patternfly/react-core'
import type { ReactNode } from 'react'

interface CreateResourceModalProps {
  isOpen: boolean
  title: string
  onClose: () => void
  onSubmit: () => void
  submitLabel?: string
  children: ReactNode
  isSubmitDisabled?: boolean
  variant?: ModalVariant
}

export function CreateResourceModal({
  isOpen,
  title,
  onClose,
  onSubmit,
  submitLabel = 'Create',
  children,
  isSubmitDisabled,
  variant = ModalVariant.medium,
}: CreateResourceModalProps) {
  return (
    <Modal
      variant={variant}
      isOpen={isOpen}
      onClose={onClose}
      aria-labelledby="create-resource-title"
    >
      <ModalHeader title={title} labelId="create-resource-title" />
      <ModalBody>
        <Form
          onSubmit={(e) => {
            e.preventDefault()
            if (!isSubmitDisabled) onSubmit()
          }}
        >
          {children}
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button key="submit" variant="primary" onClick={onSubmit} isDisabled={isSubmitDisabled}>
          {submitLabel}
        </Button>
        <Button key="cancel" variant="link" onClick={onClose}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
