import { useState } from 'react'
import {
  Button,
  Divider,
  Dropdown,
  DropdownItem,
  DropdownList,
  Masthead,
  MastheadBrand,
  MastheadContent,
  MastheadLogo,
  MastheadMain,
  MastheadToggle,
  MenuToggle,
  PageToggleButton,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from '@patternfly/react-core'
import BarsIcon from '@patternfly/react-icons/dist/esm/icons/bars-icon'
import MoonIcon from '@patternfly/react-icons/dist/esm/icons/moon-icon'
import SunIcon from '@patternfly/react-icons/dist/esm/icons/sun-icon'
import UserIcon from '@patternfly/react-icons/dist/esm/icons/user-icon'
import { AccountProvidersModal } from '@/components/modals/AccountProvidersModal'
import { AdminPanelModal } from '@/components/modals/AdminPanelModal'
import { OrgSettingsModal } from '@/components/modals/OrgSettingsModal'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useAuthStore } from '@/store/authStore'

export function AppMasthead() {
  const theme = usePlaygroundStore((s) => s.theme)
  const toggleTheme = usePlaygroundStore((s) => s.toggleTheme)
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)
  const setSidebarOpen = usePlaygroundStore((s) => s.setSidebarOpen)
  const user = useAuthStore((s) => s.user)
  const org = useAuthStore((s) => s.org)
  const orgs = useAuthStore((s) => s.orgs)
  const demoMode = useAuthStore((s) => s.demoMode)
  const logout = useAuthStore((s) => s.logout)
  const setLoginOpen = useAuthStore((s) => s.setLoginOpen)
  const switchOrg = useAuthStore((s) => s.switchOrg)

  const [userOpen, setUserOpen] = useState(false)
  const [orgOpen, setOrgOpen] = useState(false)
  const [providersOpen, setProvidersOpen] = useState(false)
  const [orgSettingsOpen, setOrgSettingsOpen] = useState(false)
  const [adminOpen, setAdminOpen] = useState(false)

  return (
    <>
      <Masthead id="page-masthead">
        <MastheadMain>
          <MastheadToggle>
            <PageToggleButton
              variant="plain"
              aria-label={isSidebarOpen ? 'Close navigation' : 'Open navigation'}
              id="navToggle"
              isSidebarOpen={isSidebarOpen}
              onSidebarToggle={() => {
                const open = usePlaygroundStore.getState().isSidebarOpen
                setSidebarOpen(!open)
              }}
            >
              <BarsIcon />
            </PageToggleButton>
          </MastheadToggle>
          <MastheadBrand>
            <MastheadLogo
              href="/"
              className="masthead-brand-text"
              onClick={(e) => e.preventDefault()}
            >
              Project<span>Everflow</span>
            </MastheadLogo>
          </MastheadBrand>
        </MastheadMain>
        <MastheadContent>
          <Toolbar id="page-toolbar" isStatic>
            <ToolbarContent>
              <ToolbarGroup
                align={{ default: 'alignEnd' }}
                gap={{ default: 'gapMd' }}
                alignItems="center"
              >
                {!demoMode && user && org ? (
                  <ToolbarItem>
                    <Dropdown
                      isOpen={orgOpen}
                      onOpenChange={setOrgOpen}
                      onSelect={() => setOrgOpen(false)}
                      toggle={(toggleRef) => (
                        <MenuToggle
                          ref={toggleRef}
                          variant="secondary"
                          onClick={() => setOrgOpen(!orgOpen)}
                          isExpanded={orgOpen}
                        >
                          {org.name}
                        </MenuToggle>
                      )}
                    >
                      <DropdownList>
                        {orgs.map((o) => (
                          <DropdownItem
                            key={o.id}
                            onClick={() => void switchOrg(o.id)}
                            isDisabled={o.id === org.id}
                          >
                            {o.name}
                          </DropdownItem>
                        ))}
                        <DropdownItem
                          key="org-settings"
                          onClick={() => setOrgSettingsOpen(true)}
                        >
                          Organization settings…
                        </DropdownItem>
                      </DropdownList>
                    </Dropdown>
                  </ToolbarItem>
                ) : null}
                <ToolbarItem>
                  <Button
                    variant="plain"
                    aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                    title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
                    onClick={() => toggleTheme()}
                  >
                    {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
                  </Button>
                </ToolbarItem>
                <ToolbarItem>
                  <Divider orientation={{ default: 'vertical' }} />
                </ToolbarItem>
                <ToolbarItem>
                  <Dropdown
                    isOpen={userOpen}
                    onOpenChange={setUserOpen}
                    onSelect={() => setUserOpen(false)}
                    toggle={(toggleRef) => (
                      <MenuToggle
                        ref={toggleRef}
                        className="pg-user-toggle"
                        variant="plain"
                        icon={<UserIcon />}
                        isFullHeight
                        onClick={() => setUserOpen(!userOpen)}
                        isExpanded={userOpen}
                      >
                        {demoMode ? 'demo' : user?.email || 'Sign in'}
                      </MenuToggle>
                    )}
                  >
                    <DropdownList>
                      {demoMode ? (
                        <DropdownItem key="demo" isDisabled>
                          Demo mode (VITE_DEMO_MODE)
                        </DropdownItem>
                      ) : user ? (
                        <>
                          <DropdownItem key="email" isDisabled>
                            {user.email}
                          </DropdownItem>
                          <DropdownItem
                            key="providers"
                            onClick={() => setProvidersOpen(true)}
                          >
                            AI providers…
                          </DropdownItem>
                          <DropdownItem
                            key="org"
                            onClick={() => setOrgSettingsOpen(true)}
                          >
                            Organization & Git…
                          </DropdownItem>
                          {user.is_superuser ? (
                            <DropdownItem key="admin" onClick={() => setAdminOpen(true)}>
                              Platform admin…
                            </DropdownItem>
                          ) : null}
                          <DropdownItem key="logout" onClick={() => logout()}>
                            Sign out
                          </DropdownItem>
                        </>
                      ) : (
                        <DropdownItem key="login" onClick={() => setLoginOpen(true)}>
                          Sign in
                        </DropdownItem>
                      )}
                    </DropdownList>
                  </Dropdown>
                </ToolbarItem>
              </ToolbarGroup>
            </ToolbarContent>
          </Toolbar>
        </MastheadContent>
      </Masthead>
      {!demoMode && user ? (
        <>
          <AccountProvidersModal
            isOpen={providersOpen}
            onClose={() => setProvidersOpen(false)}
          />
          <OrgSettingsModal
            isOpen={orgSettingsOpen}
            onClose={() => setOrgSettingsOpen(false)}
          />
          <AdminPanelModal isOpen={adminOpen} onClose={() => setAdminOpen(false)} />
        </>
      ) : null}
    </>
  )
}
