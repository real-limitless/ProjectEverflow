import { useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextInput,
} from '@patternfly/react-core'
import CheckCircleIcon from '@patternfly/react-icons/dist/esm/icons/check-circle-icon'
import ExclamationTriangleIcon from '@patternfly/react-icons/dist/esm/icons/exclamation-triangle-icon'
import { slugifyOrg } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

export function SetupWizardModal() {
  const setupOpen = useAuthStore((s) => s.setupOpen)
  const setupStatus = useAuthStore((s) => s.setupStatus)
  const busy = useAuthStore((s) => s.busy)
  const error = useAuthStore((s) => s.error)
  const completeSetup = useAuthStore((s) => s.completeSetup)
  const clearError = useAuthStore((s) => s.clearError)

  const [step, setStep] = useState(0)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('My Organization')
  const [orgSlug, setOrgSlug] = useState('my-organization')

  const sandbox = setupStatus?.sandbox
  const warnings = setupStatus?.warnings ?? []

  const checks = useMemo(() => {
    const items: { ok: boolean; label: string }[] = [
      { ok: true, label: 'Platform API reachable' },
      {
        ok: sandbox?.enabled === false || sandbox?.reachable === true,
        label:
          sandbox?.enabled === false
            ? 'Sandbox disabled (dev)'
            : sandbox?.reachable
              ? 'Sandbox agent reachable'
              : `Sandbox agent unreachable${sandbox?.error ? `: ${sandbox.error}` : ''}`,
      },
    ]
    if (sandbox?.mock) {
      items.push({
        ok: false,
        label: 'Sandbox is in mock mode (not for product use)',
      })
    }
    return items
  }, [sandbox])

  if (!setupOpen) return null

  const submit = async () => {
    clearError()
    await completeSetup({
      email: email.trim(),
      password,
      org_name: orgName.trim(),
      org_slug: orgSlug.trim(),
    })
  }

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen
      onClose={() => {
        /* first-run gate — no dismiss */
      }}
      aria-labelledby="setup-title"
    >
      <ModalHeader
        title="Welcome to Everflow"
        labelId="setup-title"
        description="First-run setup for this self-hosted instance."
      />
      <ModalBody>
        {step === 0 ? (
          <div className="setup-checks">
            <p>Host checks before creating the platform admin.</p>
            <ul className="setup-check-list">
              {checks.map((c) => (
                <li key={c.label} className={c.ok ? 'setup-check-ok' : 'setup-check-warn'}>
                  {c.ok ? <CheckCircleIcon /> : <ExclamationTriangleIcon />} {c.label}
                </li>
              ))}
            </ul>
            {warnings.length > 0 ? (
              <Alert
                variant="warning"
                isInline
                title="Configuration warnings"
                className="auth-alert"
              >
                <ul>
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </Alert>
            ) : null}
            <HelperText>
              <HelperTextItem>
                Optional: set GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET in .env for Sign in with
                GitHub, then restart the API.
              </HelperTextItem>
            </HelperText>
          </div>
        ) : null}

        {step === 1 ? (
          <Form>
            {error ? (
              <Alert variant="danger" title={error} isInline className="auth-alert" />
            ) : null}
            <FormGroup label="Admin email" fieldId="setup-email" isRequired>
              <TextInput
                id="setup-email"
                type="email"
                value={email}
                onChange={(_e, v) => {
                  setEmail(v)
                  if (!orgSlug || orgSlug === slugifyOrg(email)) {
                    setOrgSlug(slugifyOrg(v || 'admin'))
                  }
                }}
                isRequired
              />
            </FormGroup>
            <FormGroup label="Password" fieldId="setup-password" isRequired>
              <TextInput
                id="setup-password"
                type="password"
                value={password}
                onChange={(_e, v) => setPassword(v)}
                isRequired
              />
              <p className="auth-password-hint">At least 8 characters</p>
            </FormGroup>
            <FormGroup label="Organization name" fieldId="setup-org-name" isRequired>
              <TextInput
                id="setup-org-name"
                value={orgName}
                onChange={(_e, v) => setOrgName(v)}
                isRequired
              />
            </FormGroup>
            <FormGroup label="Organization slug" fieldId="setup-org-slug" isRequired>
              <TextInput
                id="setup-org-slug"
                value={orgSlug}
                onChange={(_e, v) => setOrgSlug(v.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
                isRequired
              />
            </FormGroup>
          </Form>
        ) : null}

        {step === 2 ? (
          <div>
            <p>You&apos;re ready. After setup:</p>
            <ol>
              <li>Invite teammates from the organization menu</li>
              <li>Add a GitHub PAT under Settings → Git credentials</li>
              <li>Create your first project</li>
            </ol>
            {error ? (
              <Alert variant="danger" title={error} isInline className="auth-alert" />
            ) : null}
          </div>
        ) : null}
      </ModalBody>
      <ModalFooter>
        {step > 0 ? (
          <Button variant="secondary" onClick={() => setStep(step - 1)} isDisabled={busy}>
            Back
          </Button>
        ) : null}
        {step < 2 ? (
          <Button
            variant="primary"
            onClick={() => setStep(step + 1)}
            isDisabled={
              step === 1 && (!email.trim() || password.length < 8 || !orgName.trim() || !orgSlug.trim())
            }
          >
            Continue
          </Button>
        ) : (
          <Button
            variant="primary"
            onClick={() => void submit()}
            isLoading={busy}
            isDisabled={busy}
          >
            Create admin & organization
          </Button>
        )}
      </ModalFooter>
    </Modal>
  )
}
