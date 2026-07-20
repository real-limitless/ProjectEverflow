import { useEffect, useState } from 'react'
import { Modal, ModalBody, ModalVariant } from '@patternfly/react-core'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { CreateProjectWizard } from './create-project/CreateProjectWizard'

export function CreateProjectModal() {
  const isOpen = usePlaygroundStore((s) => s.createProjectModal)
  const setOpen = usePlaygroundStore((s) => s.setCreateProjectModal)
  // Remount wizard when opened so draft resets
  const [instance, setInstance] = useState(0)

  useEffect(() => {
    if (isOpen) setInstance((n) => n + 1)
  }, [isOpen])

  return (
    <Modal
      variant={ModalVariant.large}
      isOpen={isOpen}
      // WizardHeader provides the close control; omit onClose so PF does not
      // also render .pf-v6-c-modal-box__close (duplicate X).
      onEscapePress={() => setOpen(false)}
      aria-label="Create project wizard"
      className="create-project-modal"
    >
      <ModalBody className="create-project-modal-body">
        {isOpen ? (
          <CreateProjectWizard
            key={instance}
            onClose={() => setOpen(false)}
          />
        ) : null}
      </ModalBody>
    </Modal>
  )
}
