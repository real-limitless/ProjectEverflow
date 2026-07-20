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
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  PageToggleButton,
  TextInput,
  Toolbar,
  ToolbarContent,
  ToolbarGroup,
  ToolbarItem,
} from '@patternfly/react-core'
import BarsIcon from '@patternfly/react-icons/dist/esm/icons/bars-icon'
import MoonIcon from '@patternfly/react-icons/dist/esm/icons/moon-icon'
import SunIcon from '@patternfly/react-icons/dist/esm/icons/sun-icon'
import UserIcon from '@patternfly/react-icons/dist/esm/icons/user-icon'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { NamedLayoutSnapshot } from '@/lib/namedLayouts'

export function AppMasthead() {
  const resetLayout = usePlaygroundStore((s) => s.resetLayout)
  const saveNamedLayout = usePlaygroundStore((s) => s.saveNamedLayout)
  const loadNamedLayout = usePlaygroundStore((s) => s.loadNamedLayout)
  const deleteNamedLayout = usePlaygroundStore((s) => s.deleteNamedLayout)
  const listNamedLayouts = usePlaygroundStore((s) => s.listNamedLayouts)
  const theme = usePlaygroundStore((s) => s.theme)
  const toggleTheme = usePlaygroundStore((s) => s.toggleTheme)
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)
  const setSidebarOpen = usePlaygroundStore((s) => s.setSidebarOpen)

  const [layoutOpen, setLayoutOpen] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [loadOpen, setLoadOpen] = useState(false)
  const [layoutName, setLayoutName] = useState('')
  const [saved, setSaved] = useState<NamedLayoutSnapshot[]>([])

  const openLoad = () => {
    setSaved(listNamedLayouts())
    setLoadOpen(true)
    setLayoutOpen(false)
  }

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
                // Always read latest store value (avoid dual-mode / stale state)
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
                <ToolbarItem>
                  <Dropdown
                    isOpen={layoutOpen}
                    onOpenChange={setLayoutOpen}
                    onSelect={() => setLayoutOpen(false)}
                    toggle={(toggleRef) => (
                      <MenuToggle
                        ref={toggleRef}
                        onClick={() => setLayoutOpen(!layoutOpen)}
                        isExpanded={layoutOpen}
                        variant="secondary"
                      >
                        Layout
                      </MenuToggle>
                    )}
                  >
                    <DropdownList>
                      <DropdownItem
                        key="save"
                        onClick={() => {
                          setLayoutName('')
                          setSaveOpen(true)
                        }}
                      >
                        Save layout…
                      </DropdownItem>
                      <DropdownItem key="load" onClick={openLoad}>
                        Load layout…
                      </DropdownItem>
                      <DropdownItem key="reset" onClick={() => resetLayout()}>
                        Reset to default
                      </DropdownItem>
                    </DropdownList>
                  </Dropdown>
                </ToolbarItem>
                <ToolbarItem>
                  <Divider orientation={{ default: 'vertical' }} />
                </ToolbarItem>
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
                  <MenuToggle
                    className="pg-user-toggle"
                    variant="plain"
                    icon={<UserIcon />}
                    isFullHeight
                  >
                    admin
                  </MenuToggle>
                </ToolbarItem>
              </ToolbarGroup>
            </ToolbarContent>
          </Toolbar>
        </MastheadContent>
      </Masthead>

      <Modal
        variant={ModalVariant.small}
        isOpen={saveOpen}
        onClose={() => setSaveOpen(false)}
        aria-labelledby="save-layout-title"
      >
        <ModalHeader title="Save layout" labelId="save-layout-title" />
        <ModalBody>
          <TextInput
            id="layout-name"
            value={layoutName}
            onChange={(_e, v) => setLayoutName(v)}
            placeholder="e.g. Coding focus"
            aria-label="Layout name"
          />
        </ModalBody>
        <ModalFooter>
          <Button
            variant="primary"
            isDisabled={!layoutName.trim()}
            onClick={() => {
              saveNamedLayout(layoutName)
              setSaveOpen(false)
            }}
          >
            Save
          </Button>
          <Button variant="link" onClick={() => setSaveOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>

      <Modal
        variant={ModalVariant.medium}
        isOpen={loadOpen}
        onClose={() => setLoadOpen(false)}
        aria-labelledby="load-layout-title"
      >
        <ModalHeader title="Load layout" labelId="load-layout-title" />
        <ModalBody>
          {saved.length === 0 ? (
            <p style={{ color: 'var(--pf-t--global--text--color--subtle)' }}>
              No saved layouts yet. Use Layout → Save layout…
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {saved.map((s) => (
                <div
                  key={s.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    justifyContent: 'space-between',
                    border:
                      '1px solid var(--pf-t--global--border--color--default)',
                    borderRadius: 6,
                    padding: '8px 12px',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 600 }}>{s.name}</div>
                    <div
                      style={{
                        fontSize: 12,
                        color: 'var(--pf-t--global--text--color--subtle)',
                      }}
                    >
                      {new Date(s.savedAt).toLocaleString()} · project {s.projectId}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => {
                        loadNamedLayout(s.id)
                        setLoadOpen(false)
                      }}
                    >
                      Load
                    </Button>
                    <Button
                      size="sm"
                      variant="link"
                      onClick={() => {
                        deleteNamedLayout(s.id)
                        setSaved(listNamedLayouts())
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="link" onClick={() => setLoadOpen(false)}>
            Close
          </Button>
        </ModalFooter>
      </Modal>
    </>
  )
}
