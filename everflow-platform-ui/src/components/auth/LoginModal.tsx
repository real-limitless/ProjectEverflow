import { useEffect, useState } from 'react'
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
import { getAuthProviders, oauthAuthorizeUrl, type AuthProviders } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

export function LoginModal() {
  const loginOpen = useAuthStore((s) => s.loginOpen)
  const setupOpen = useAuthStore((s) => s.setupOpen)
  const demoMode = useAuthStore((s) => s.demoMode)
  const busy = useAuthStore((s) => s.busy)
  const error = useAuthStore((s) => s.error)
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const clearError = useAuthStore((s) => s.clearError)
  const pendingInvite = useAuthStore((s) => s.pendingInvite)

  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [providers, setProviders] = useState<AuthProviders | null>(null)

  useEffect(() => {
    if (!loginOpen) return
    void getAuthProviders()
      .then(setProviders)
      .catch(() => setProviders({ github: false, google: false, password: true }))
  }, [loginOpen])

  if (demoMode || setupOpen) return null

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
        description={
          pendingInvite
            ? 'Sign in or register to accept your organization invite.'
            : 'Projects run in isolated sandboxes on your host. Sign in to continue.'
        }
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
        {providers?.github || providers?.google ? (
          <div className="auth-oauth-row">
            {providers.github ? (
              <Button
                variant="secondary"
                component="a"
                href={oauthAuthorizeUrl('github')}
              >
                Sign in with GitHub
              </Button>
            ) : null}
            {providers.google ? (
              <Button
                variant="secondary"
                component="a"
                href={oauthAuthorizeUrl('google')}
              >
                Sign in with Google
              </Button>
            ) : null}
          </div>
        ) : null}
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
