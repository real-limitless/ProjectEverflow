import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Tab,
  Tabs,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import {
  ApiError,
  createOrg,
  createOrgInvite,
  listOrgMembers,
  removeOrgMember,
  slugifyOrg,
  updateOrgMemberRole,
  type OrgMember,
} from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { GitCredentialsManager } from '@/components/git/GitCredentialsManager'

interface OrgSettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function OrgSettingsModal({ isOpen, onClose }: OrgSettingsModalProps) {
  const org = useAuthStore((s) => s.org)
  const orgs = useAuthStore((s) => s.orgs)
  const user = useAuthStore((s) => s.user)
  const refreshOrgs = useAuthStore((s) => s.refreshOrgs)
  const switchOrg = useAuthStore((s) => s.switchOrg)

  const [tab, setTab] = useState<string | number>('members')
  const [members, setMembers] = useState<OrgMember[]>([])
  const [error, setError] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgSlug, setNewOrgSlug] = useState('')

  const canAdmin = org?.role === 'owner' || org?.role === 'admin'

  const loadMembers = useCallback(async () => {
    if (!org) return
    try {
      const rows = await listOrgMembers(org.id)
      setMembers(rows)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load members')
    }
  }, [org])

  useEffect(() => {
    if (isOpen && org) {
      setError('')
      setInviteUrl('')
      void loadMembers()
    }
  }, [isOpen, org, loadMembers])

  const createInvite = async () => {
    if (!org) return
    setBusy(true)
    setError('')
    try {
      const invite = await createOrgInvite(org.id, { role: 'member' })
      setInviteUrl(invite.invite_url || '')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to create invite')
    } finally {
      setBusy(false)
    }
  }

  const onRoleChange = async (member: OrgMember, role: string) => {
    if (!org) return
    try {
      await updateOrgMemberRole(org.id, member.user_id, role as 'owner' | 'admin' | 'member')
      await loadMembers()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to update role')
    }
  }

  const onRemove = async (member: OrgMember) => {
    if (!org) return
    try {
      await removeOrgMember(org.id, member.user_id)
      await loadMembers()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to remove member')
    }
  }

  const onCreateOrg = async () => {
    if (!newOrgName.trim() || !newOrgSlug.trim()) return
    setBusy(true)
    setError('')
    try {
      const created = await createOrg(newOrgName.trim(), newOrgSlug.trim())
      await refreshOrgs()
      await switchOrg(created.id)
      setNewOrgName('')
      setNewOrgSlug('')
      setTab('members')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to create organization')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      variant={ModalVariant.large}
      isOpen={isOpen}
      onClose={onClose}
      aria-labelledby="org-settings-title"
    >
      <ModalHeader
        title={org ? `${org.name} settings` : 'Organization'}
        labelId="org-settings-title"
        description={org ? `Slug: ${org.slug} · Your role: ${org.role || 'member'}` : undefined}
      />
      <ModalBody>
        {error ? <Alert variant="danger" title={error} isInline className="auth-alert" /> : null}
        <Tabs activeKey={tab} onSelect={(_e, k) => setTab(k)} aria-label="Organization settings">
          <Tab eventKey="members" title={<TabTitleText>Members</TabTitleText>}>
            <div className="org-settings-section">
              {canAdmin ? (
                <div className="org-invite-row">
                  <Button variant="secondary" onClick={() => void createInvite()} isLoading={busy}>
                    Create invite link
                  </Button>
                  {inviteUrl ? (
                    <div className="org-invite-url">
                      <TextInput
                        aria-label="Invite URL"
                        value={inviteUrl}
                        readOnly
                        onFocus={(e) => e.currentTarget.select()}
                      />
                      <Button
                        variant="primary"
                        onClick={() => void navigator.clipboard.writeText(inviteUrl)}
                      >
                        Copy
                      </Button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <table className="org-members-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id}>
                      <td>{m.email || m.user_id}</td>
                      <td>
                        {canAdmin && m.user_id !== user?.id ? (
                          <FormSelect
                            id={`role-${m.id}`}
                            value={m.role}
                            onChange={(_e, v) => void onRoleChange(m, v)}
                            aria-label={`Role for ${m.email}`}
                          >
                            <FormSelectOption value="member" label="member" />
                            <FormSelectOption value="admin" label="admin" />
                            {org?.role === 'owner' ? (
                              <FormSelectOption value="owner" label="owner" />
                            ) : null}
                          </FormSelect>
                        ) : (
                          m.role
                        )}
                      </td>
                      <td>
                        {canAdmin && m.user_id !== user?.id ? (
                          <Button variant="link" isDanger onClick={() => void onRemove(m)}>
                            Remove
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Tab>
          <Tab eventKey="git" title={<TabTitleText>Git credentials</TabTitleText>}>
            <div className="org-settings-section">
              <GitCredentialsManager scope="user" />
              {org && canAdmin ? (
                <>
                  <h3 className="org-settings-subtitle">Organization PATs</h3>
                  <GitCredentialsManager scope="org" orgId={org.id} />
                </>
              ) : null}
            </div>
          </Tab>
          <Tab eventKey="orgs" title={<TabTitleText>Organizations</TabTitleText>}>
            <div className="org-settings-section">
              <ul className="org-list">
                {orgs.map((o) => (
                  <li key={o.id}>
                    <Button
                      variant={o.id === org?.id ? 'primary' : 'secondary'}
                      onClick={() => void switchOrg(o.id)}
                    >
                      {o.name} ({o.role})
                    </Button>
                  </li>
                ))}
              </ul>
              <Form className="org-create-form">
                <FormGroup label="New organization" fieldId="new-org-name">
                  <TextInput
                    id="new-org-name"
                    value={newOrgName}
                    onChange={(_e, v) => {
                      setNewOrgName(v)
                      setNewOrgSlug(slugifyOrg(v || 'org'))
                    }}
                  />
                </FormGroup>
                <FormGroup label="Slug" fieldId="new-org-slug">
                  <TextInput
                    id="new-org-slug"
                    value={newOrgSlug}
                    onChange={(_e, v) => setNewOrgSlug(v)}
                  />
                </FormGroup>
                <Button
                  variant="secondary"
                  onClick={() => void onCreateOrg()}
                  isDisabled={busy || !newOrgName.trim() || !newOrgSlug.trim()}
                  isLoading={busy}
                >
                  Create organization
                </Button>
              </Form>
            </div>
          </Tab>
        </Tabs>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </ModalFooter>
    </Modal>
  )
}
