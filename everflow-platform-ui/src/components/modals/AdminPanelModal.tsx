import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Tab,
  Tabs,
  TabTitleText,
} from '@patternfly/react-core'
import {
  ApiError,
  activateAdminUser,
  deactivateAdminUser,
  listAdminOrgs,
  listAdminUsers,
  type AdminOrg,
  type AdminUser,
} from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

interface AdminPanelModalProps {
  isOpen: boolean
  onClose: () => void
}

export function AdminPanelModal({ isOpen, onClose }: AdminPanelModalProps) {
  const user = useAuthStore((s) => s.user)
  const [tab, setTab] = useState<string | number>('users')
  const [users, setUsers] = useState<AdminUser[]>([])
  const [orgs, setOrgs] = useState<AdminOrg[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isOpen || !user?.is_superuser) return
    void (async () => {
      try {
        setUsers(await listAdminUsers())
        setOrgs(await listAdminOrgs())
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Failed to load admin data')
      }
    })()
  }, [isOpen, user?.is_superuser])

  if (!user?.is_superuser) return null

  const toggleActive = async (u: AdminUser) => {
    try {
      const updated = u.is_active
        ? await deactivateAdminUser(u.id)
        : await activateAdminUser(u.id)
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Update failed')
    }
  }

  return (
    <Modal
      variant={ModalVariant.large}
      isOpen={isOpen}
      onClose={onClose}
      aria-labelledby="admin-panel-title"
    >
      <ModalHeader title="Platform admin" labelId="admin-panel-title" />
      <ModalBody>
        {error ? <Alert variant="danger" title={error} isInline className="auth-alert" /> : null}
        <Tabs activeKey={tab} onSelect={(_e, k) => setTab(k)}>
          <Tab eventKey="users" title={<TabTitleText>Users</TabTitleText>}>
            <table className="org-members-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      {u.email}
                      {u.is_superuser ? ' · admin' : ''}
                    </td>
                    <td>{u.is_active ? 'active' : 'inactive'}</td>
                    <td>
                      {u.id !== user.id ? (
                        <Button variant="link" onClick={() => void toggleActive(u)}>
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Tab>
          <Tab eventKey="orgs" title={<TabTitleText>Organizations</TabTitleText>}>
            <table className="org-members-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Slug</th>
                  <th>Members</th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((o) => (
                  <tr key={o.id}>
                    <td>{o.name}</td>
                    <td>{o.slug}</td>
                    <td>{o.member_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
