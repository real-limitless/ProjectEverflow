import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  ClipboardCopy,
  Form,
  FormGroup,
  FormHelperText,
  FormSection,
  FormSelect,
  FormSelectOption,
  Grid,
  GridItem,
  HelperText,
  HelperTextItem,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Spinner,
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

type OrgSettingsTab = 'members' | 'git' | 'orgs'

interface OrgSettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

function roleLabelColor(role: string): 'blue' | 'green' | 'grey' | 'purple' {
  if (role === 'owner') return 'purple'
  if (role === 'admin') return 'green'
  return 'grey'
}

export function OrgSettingsModal({ isOpen, onClose }: OrgSettingsModalProps) {
  const org = useAuthStore((s) => s.org)
  const orgs = useAuthStore((s) => s.orgs)
  const user = useAuthStore((s) => s.user)
  const refreshOrgs = useAuthStore((s) => s.refreshOrgs)
  const switchOrg = useAuthStore((s) => s.switchOrg)

  const [tab, setTab] = useState<OrgSettingsTab>('members')
  const [members, setMembers] = useState<OrgMember[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [error, setError] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [memberBusyId, setMemberBusyId] = useState<string | null>(null)
  const [newOrgName, setNewOrgName] = useState('')
  const [newOrgSlug, setNewOrgSlug] = useState('')

  const canAdmin = org?.role === 'owner' || org?.role === 'admin'

  const loadMembers = useCallback(async () => {
    if (!org) return
    setMembersLoading(true)
    try {
      const rows = await listOrgMembers(org.id)
      setMembers(rows)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load members')
    } finally {
      setMembersLoading(false)
    }
  }, [org])

  // Reset UI when the modal opens (not on every org switch while open)
  useEffect(() => {
    if (!isOpen) return
    setError('')
    setInviteUrl('')
    setNewOrgName('')
    setNewOrgSlug('')
    setTab(org ? 'members' : 'orgs')
  }, [isOpen]) // eslint-disable-line react-hooks/exhaustive-deps -- open-only reset

  useEffect(() => {
    if (!isOpen) return
    if (org) {
      void loadMembers()
    } else {
      setMembers([])
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
    setMemberBusyId(member.id)
    setError('')
    try {
      await updateOrgMemberRole(org.id, member.user_id, role as 'owner' | 'admin' | 'member')
      await loadMembers()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to update role')
    } finally {
      setMemberBusyId(null)
    }
  }

  const onRemove = async (member: OrgMember) => {
    if (!org) return
    setMemberBusyId(member.id)
    setError('')
    try {
      await removeOrgMember(org.id, member.user_id)
      await loadMembers()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to remove member')
    } finally {
      setMemberBusyId(null)
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

  const title = org
    ? `Organization settings · ${org.name}`
    : 'Organization settings'

  return (
    <Modal
      variant={ModalVariant.large}
      isOpen={isOpen}
      onClose={onClose}
      aria-labelledby="org-settings-title"
      className="project-settings-modal org-settings-modal"
    >
      <ModalHeader
        title={title}
        labelId="org-settings-title"
        description={
          org ? (
            <span className="org-settings-header-meta">
              <span className="org-settings-slug">{org.slug}</span>
              {org.role ? (
                <Label color={roleLabelColor(org.role)} isCompact>
                  {org.role}
                </Label>
              ) : null}
            </span>
          ) : (
            'Choose or create an organization to continue.'
          )
        }
      />
      <ModalBody>
        <Tabs
          activeKey={tab}
          onSelect={(_e, k) => setTab(k as OrgSettingsTab)}
          aria-label="Organization settings"
          className="project-settings-tabs"
        >
          <Tab eventKey="members" title={<TabTitleText>Members</TabTitleText>} />
          <Tab eventKey="git" title={<TabTitleText>Git credentials</TabTitleText>} />
          <Tab eventKey="orgs" title={<TabTitleText>Organizations</TabTitleText>} />
        </Tabs>

        <div className="project-settings-body">
          {error ? (
            <Alert
              variant="danger"
              isInline
              isPlain
              title={error}
              className="project-settings-alert"
              role="alert"
            />
          ) : null}

          {tab === 'members' && (
            <div className="org-settings-panel">
              {!org ? (
                <p className="project-settings-lead">
                  Select an organization on the Organizations tab to manage members.
                </p>
              ) : (
                <>
                  <p className="project-settings-lead">
                    Invite teammates and manage who can administer this organization. Owners and
                    admins can manage members and organization Git tokens.
                  </p>

                  {canAdmin ? (
                    <FormSection title="Invite people" titleElement="h2">
                      <p className="org-settings-section-lead">
                        Create a one-time invite link. New joiners receive the{' '}
                        <strong>member</strong> role.
                      </p>
                      <div className="org-invite-actions">
                        <Button
                          variant="secondary"
                          onClick={() => void createInvite()}
                          isLoading={busy}
                        >
                          Create invite link
                        </Button>
                      </div>
                      {inviteUrl ? (
                        <div className="org-invite-copy">
                          <ClipboardCopy isReadOnly hoverTip="Copy" clickTip="Copied">
                            {inviteUrl}
                          </ClipboardCopy>
                        </div>
                      ) : null}
                    </FormSection>
                  ) : null}

                  <FormSection title="Members" titleElement="h2">
                    {membersLoading ? (
                      <div className="org-settings-loading">
                        <Spinner size="lg" aria-label="Loading members" />
                      </div>
                    ) : members.length === 0 ? (
                      <p className="org-settings-empty">
                        No members found. Create an invite link to bring people into this
                        organization.
                      </p>
                    ) : (
                      <ul className="org-settings-cards" aria-label="Organization members">
                        {members.map((m) => {
                          const isSelf = m.user_id === user?.id
                          const rowBusy = memberBusyId === m.id
                          return (
                            <li key={m.id} className="org-settings-card">
                              <div className="org-settings-card-main">
                                <div className="org-settings-card-title">
                                  {m.email || m.user_id}
                                  {isSelf ? (
                                    <span className="org-settings-card-you"> · you</span>
                                  ) : null}
                                </div>
                                <div className="org-settings-card-meta">
                                  <Label color={roleLabelColor(m.role)} isCompact>
                                    {m.role}
                                  </Label>
                                </div>
                              </div>
                              {canAdmin && !isSelf ? (
                                <div className="org-settings-card-actions">
                                  <FormSelect
                                    id={`role-${m.id}`}
                                    value={m.role}
                                    isDisabled={rowBusy}
                                    onChange={(_e, v) => void onRoleChange(m, v)}
                                    aria-label={`Role for ${m.email || m.user_id}`}
                                    className="org-role-select"
                                  >
                                    <FormSelectOption value="member" label="member" />
                                    <FormSelectOption value="admin" label="admin" />
                                    {org.role === 'owner' ? (
                                      <FormSelectOption value="owner" label="owner" />
                                    ) : null}
                                  </FormSelect>
                                  <Button
                                    variant="link"
                                    isDanger
                                    isDisabled={rowBusy}
                                    onClick={() => void onRemove(m)}
                                  >
                                    Remove
                                  </Button>
                                </div>
                              ) : null}
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </FormSection>
                </>
              )}
            </div>
          )}

          {tab === 'git' && (
            <div className="org-settings-panel">
              <p className="project-settings-lead">
                Personal access tokens authenticate Git clones for your account. Organization
                tokens are shared for team workflows and can only be managed by owners and admins.
              </p>

              <FormSection title="Your personal tokens" titleElement="h2">
                <GitCredentialsManager
                  scope="user"
                  lead="Used when you connect or clone repositories as yourself."
                />
              </FormSection>

              <FormSection title="Organization tokens" titleElement="h2">
                {org && canAdmin ? (
                  <GitCredentialsManager
                    scope="org"
                    orgId={org.id}
                    lead={`Shared GitHub PATs for ${org.name}. Prefer a bot or machine-user token with least privilege.`}
                  />
                ) : org ? (
                  <p className="org-settings-empty">
                    Only owners and admins can manage organization Git tokens. You can still add
                    personal tokens above.
                  </p>
                ) : (
                  <p className="org-settings-empty">
                    Select an organization to manage shared Git tokens.
                  </p>
                )}
              </FormSection>
            </div>
          )}

          {tab === 'orgs' && (
            <div className="org-settings-panel">
              <p className="project-settings-lead">
                Switch the active organization or create a new one. Projects and sandboxes are
                scoped to the organization you select.
              </p>

              {org ? (
                <FormSection title="Current organization" titleElement="h2">
                  <div className="org-settings-card org-settings-card--current">
                    <div className="org-settings-card-main">
                      <div className="org-settings-card-title">
                        {org.name}
                        <Label color="blue" isCompact className="org-current-chip">
                          Current
                        </Label>
                      </div>
                      <div className="org-settings-card-meta org-settings-card-meta--plain">
                        <span className="org-settings-slug">{org.slug}</span>
                        {org.role ? (
                          <Label color={roleLabelColor(org.role)} isCompact>
                            {org.role}
                          </Label>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </FormSection>
              ) : null}

              <FormSection title="Your organizations" titleElement="h2">
                {orgs.length === 0 ? (
                  <p className="org-settings-empty">
                    You are not a member of any organization yet. Create one below.
                  </p>
                ) : (
                  <ul className="org-settings-cards" aria-label="Your organizations">
                    {orgs.map((o) => {
                      const isCurrent = o.id === org?.id
                      return (
                        <li
                          key={o.id}
                          className={`org-settings-card${isCurrent ? ' org-settings-card--current' : ''}`}
                        >
                          <div className="org-settings-card-main">
                            <div className="org-settings-card-title">{o.name}</div>
                            <div className="org-settings-card-meta org-settings-card-meta--plain">
                              <span className="org-settings-slug">{o.slug}</span>
                              {o.role ? (
                                <Label color={roleLabelColor(o.role)} isCompact>
                                  {o.role}
                                </Label>
                              ) : null}
                            </div>
                          </div>
                          <div className="org-settings-card-actions">
                            <Button
                              variant={isCurrent ? 'primary' : 'secondary'}
                              isDisabled={isCurrent}
                              onClick={() => void switchOrg(o.id)}
                            >
                              {isCurrent ? 'Selected' : 'Switch'}
                            </Button>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </FormSection>

              <FormSection title="Create organization" titleElement="h2">
                <Form className="project-settings-form org-create-form">
                  <Grid hasGutter md={6}>
                    <GridItem span={12} md={6}>
                      <FormGroup label="Name" fieldId="new-org-name" isRequired>
                        <TextInput
                          id="new-org-name"
                          value={newOrgName}
                          onChange={(_e, v) => {
                            setNewOrgName(v)
                            setNewOrgSlug(slugifyOrg(v || 'org'))
                          }}
                          aria-label="New organization name"
                        />
                      </FormGroup>
                    </GridItem>
                    <GridItem span={12} md={6}>
                      <FormGroup label="Slug" fieldId="new-org-slug" isRequired>
                        <TextInput
                          id="new-org-slug"
                          value={newOrgSlug}
                          onChange={(_e, v) => setNewOrgSlug(v)}
                          aria-label="New organization slug"
                        />
                        <FormHelperText>
                          <HelperText>
                            <HelperTextItem>
                              URL-safe identifier (lowercase letters, numbers, hyphens). Must be
                              unique.
                            </HelperTextItem>
                          </HelperText>
                        </FormHelperText>
                      </FormGroup>
                    </GridItem>
                    <GridItem span={12}>
                      <Button
                        variant="secondary"
                        onClick={() => void onCreateOrg()}
                        isDisabled={busy || !newOrgName.trim() || !newOrgSlug.trim()}
                        isLoading={busy}
                      >
                        Create organization
                      </Button>
                    </GridItem>
                  </Grid>
                </Form>
              </FormSection>
            </div>
          )}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </ModalFooter>
    </Modal>
  )
}
