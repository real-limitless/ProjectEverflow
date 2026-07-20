import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
} from '@patternfly/react-core'
import { getProject, listProjectIds } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function OpenProjectModal() {
  const isOpen = usePlaygroundStore((s) => s.openProjectModal)
  const setOpen = usePlaygroundStore((s) => s.setOpenProjectModal)
  const setCreate = usePlaygroundStore((s) => s.setCreateProjectModal)
  const openProject = usePlaygroundStore((s) => s.openProject)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  void catalogVersion

  const projectIds = listProjectIds()

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={() => setOpen(false)}
      aria-labelledby="openProjectModalTitle"
    >
      <ModalHeader title="Open project" labelId="openProjectModalTitle" />
      <ModalBody>
        {projectIds.length === 0 ? (
          <p style={{ margin: 0 }}>
            No projects yet. Create a project to get started.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {projectIds.map((id) => {
              const p = getProject(id)
              if (!p) return null
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
        )}
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={() => {
            setOpen(false)
            setCreate(true)
          }}
        >
          Create project
        </Button>
        <Button variant="link" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
