import { useState } from 'react'
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

export function ConnectRepoModal() {
  const isOpen = usePlaygroundStore((s) => s.connectRepoModal)
  const setOpen = usePlaygroundStore((s) => s.setConnectRepoModal)
  const [url, setUrl] = useState('')

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={isOpen}
      onClose={() => setOpen(false)}
      aria-labelledby="connectModalTitle"
    >
      <ModalHeader title="Connect a repository" labelId="connectModalTitle" />
      <ModalBody>
        <Form>
          <FormGroup label="Repository URL" fieldId="repoUrl">
            <TextInput
              id="repoUrl"
              value={url}
              onChange={(_e, v) => setUrl(v)}
              placeholder="https://github.com/you/awesome-app.git"
            />
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={() => {
            alert(
              url
                ? `Demo: would connect ${url}`
                : 'Demo: enter a repository URL',
            )
            setOpen(false)
            setUrl('')
          }}
        >
          Connect
        </Button>
        <Button variant="link" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
