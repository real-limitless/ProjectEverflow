import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
} from '@patternfly/react-core'
import { PROJECTS, PROJECT_IDS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function OpenProjectModal() {
  const isOpen = usePlaygroundStore((s) => s.openProjectModal)
  const setOpen = usePlaygroundStore((s) => s.setOpenProjectModal)
  const openProject = usePlaygroundStore((s) => s.openProject)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={() => setOpen(false)}
      aria-labelledby="openProjectModalTitle"
    >
      <ModalHeader title="Open project" labelId="openProjectModalTitle" />
      <ModalBody>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {PROJECT_IDS.map((id) => {
            const p = PROJECTS[id]
            const already = openProjectIds.includes(id)
            return (
              <Button
                key={id}
                variant={already ? 'secondary' : 'primary'}
                isBlock
                onClick={() => openProject(id)}
              >
                {p.name}
                {already ? ' (open)' : ''}
              </Button>
            )
          })}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button variant="link" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
