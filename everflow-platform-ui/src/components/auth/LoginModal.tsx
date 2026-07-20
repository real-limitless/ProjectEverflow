import { useState } from 'react'
import {
  Alert,
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
import { useAuthStore } from '@/store/authStore'

export function LoginModal() {
  const loginOpen = useAuthStore((s) => s.loginOpen)
  const demoMode = useAuthStore((s) => s.demoMode)
  const busy = useAuthStore((s) => s.busy)
  const error = useAuthStore((s) => s.error)
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const clearError = useAuthStore((s) => s.clearError)

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  if (demoMode) return null

  const submit = async () => {
    clearError()
    if (!email.trim() || password.length < 8) return
    if (mode === 'login') await login(email, password)
    else await register(email, password)
  }

  return (
    <Modal
      variant={ModalVariant.small}
      isOpen={loginOpen}
      onClose={() => {
        /* require auth — no dismiss without session */
      }}
      aria-labelledby="auth-title"
      disableFocusTrap={false}
    >
      <ModalHeader
        title={mode === 'login' ? 'Sign in to Everflow' : 'Create account'}
        labelId="auth-title"
        description="Projects run in isolated sandboxes on your host. Sign in to continue."
      />
      <ModalBody>
        <Form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          {error ? (
            <Alert variant="danger" title={error} isInline className="auth-alert" />
          ) : null}
          <FormGroup label="Email" fieldId="auth-email" isRequired>
            <TextInput
              id="auth-email"
              type="email"
              value={email}
              onChange={(_e, v) => setEmail(v)}
              autoComplete="username"
              isRequired
            />
          </FormGroup>
          <FormGroup label="Password" fieldId="auth-password" isRequired>
            <TextInput
              id="auth-password"
              type="password"
              value={password}
              onChange={(_e, v) => setPassword(v)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              isRequired
              validated={password.length > 0 && password.length < 8 ? 'error' : 'default'}
            />
            <p className="auth-password-hint">At least 8 characters</p>
          </FormGroup>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={() => void submit()}
          isLoading={busy}
          isDisabled={busy || !email.trim() || password.length < 8}
        >
          {mode === 'login' ? 'Sign in' : 'Register'}
        </Button>
        <Button
          variant="link"
          onClick={() => {
            clearError()
            setMode(mode === 'login' ? 'register' : 'login')
          }}
          isDisabled={busy}
        >
          {mode === 'login' ? 'Need an account? Register' : 'Have an account? Sign in'}
        </Button>
      </ModalFooter>
    </Modal>
  )
}
