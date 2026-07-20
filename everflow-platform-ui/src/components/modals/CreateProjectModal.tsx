import { useEffect, useState } from 'react'
import {
  Button,
  Form,
  FormGroup,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextInput,
} from '@patternfly/react-core'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function CreateProjectModal() {
  const isOpen = usePlaygroundStore((s) => s.createProjectModal)
  const setOpen = usePlaygroundStore((s) => s.setCreateProjectModal)
  const createProject = usePlaygroundStore((s) => s.createProject)
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (isOpen) {
      setName('')
      setError('')
    }
  }, [isOpen])

  const submit = () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Enter a project name')
      return
    }
    const id = createProject(trimmed)
    if (!id) setError('Could not create project')
  }

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={() => setOpen(false)}
      aria-labelledby="createProjectModalTitle"
    >
      <ModalHeader title="Create project" labelId="createProjectModalTitle" />
      <ModalBody>
        <Form
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <FormGroup label="Project name" isRequired fieldId="create-project-name">
            <TextInput
              id="create-project-name"
              value={name}
              onChange={(_e, v) => {
                setName(v)
                if (error) setError('')
              }}
              placeholder="e.g. My app"
              autoFocus
              validated={error ? 'error' : 'default'}
            />
            {error ? (
              <div className="pf-v6-c-form__helper-text pf-m-error" style={{ marginTop: 6 }}>
                {error}
              </div>
            ) : null}
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={submit}>
          Create
        </Button>
        <Button variant="link" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
