import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  TextInput,
} from '@patternfly/react-core'
import CogIcon from '@patternfly/react-icons/dist/esm/icons/cog-icon'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import SaveIcon from '@patternfly/react-icons/dist/esm/icons/save-icon'
import { PROJECTS, getProject } from '@/data/projects'
import { getSandboxStatus, isDemoMode } from '@/lib/api'
import type { NamedLayoutSnapshot } from '@/lib/namedLayouts'
import { usePlaygroundStore } from '@/store/playgroundStore'

interface ContextMenuState {
  projectId: string
  x: number
  y: number
}

export function ProjectTabBar() {
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const switchProject = usePlaygroundStore((s) => s.switchProject)
  const closeProjectTab = usePlaygroundStore((s) => s.closeProjectTab)
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)
  const openProjectSettings = usePlaygroundStore((s) => s.openProjectSettings)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const resetLayout = usePlaygroundStore((s) => s.resetLayout)
  const saveNamedLayout = usePlaygroundStore((s) => s.saveNamedLayout)
  const loadNamedLayout = usePlaygroundStore((s) => s.loadNamedLayout)
  const deleteNamedLayout = usePlaygroundStore((s) => s.deleteNamedLayout)
  const listNamedLayouts = usePlaygroundStore((s) => s.listNamedLayouts)

  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [layoutOpen, setLayoutOpen] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [loadOpen, setLoadOpen] = useState(false)
  const [layoutName, setLayoutName] = useState('')
  const [saved, setSaved] = useState<NamedLayoutSnapshot[]>([])

  // Touch catalogVersion so renames refresh tab labels
  void catalogVersion

  // Keep sandbox status fresh for the active project (no UI chip — status is the tab orb only)
  const currentProject = getProject(currentProjectId)
  const sandboxStatus = currentProject?.sandboxStatus
  useEffect(() => {
    if (!currentProjectId || !currentProject?.fromApi || isDemoMode()) return
    let cancelled = false
    const tick = async () => {
      try {
        const st = await getSandboxStatus(currentProjectId)
        if (cancelled) return
        patchProjectSandbox(currentProjectId, {
          sandboxStatus: st.status,
          sandboxName: st.sandbox_name,
          sandboxError: st.error,
          sandboxImage: st.image,
          sandboxCreatedAt: st.created_at,
        })
      } catch {
        /* ignore */
      }
    }
    void tick()
    const interval =
      sandboxStatus === 'running'
        ? 15000
        : sandboxStatus === 'pending' || sandboxStatus === 'creating'
          ? 2000
          : 5000
    const id = window.setInterval(() => void tick(), interval)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [
    currentProjectId,
    currentProject?.fromApi,
    sandboxStatus,
    patchProjectSandbox,
  ])

  useEffect(() => {
    if (!menu) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenu(null)
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [menu])

  const openCtx = (e: React.MouseEvent, projectId: string) => {
    e.preventDefault()
    e.stopPropagation()
    setMenu({ projectId, x: e.clientX, y: e.clientY })
  }

  const openLoad = () => {
    setSaved(listNamedLayouts())
    setLoadOpen(true)
    setLayoutOpen(false)
  }

  return (
    <>
      <div className="pg-project-bar">
        <div className="project-tabs" id="projectTabs">
          {openProjectIds.map((id) => {
            const p = PROJECTS[id]
            if (!p) return null
            return (
              <button
                key={id}
                type="button"
                className={`project-tab${id === currentProjectId ? ' active' : ''}`}
                onClick={() => switchProject(id)}
                onContextMenu={(e) => openCtx(e, id)}
                title={`${p.name} — right-click for project settings`}
              >
                <span className="dot" />
                <span className="pt-name">{p.name}</span>
                <span
                  className="pt-close"
                  title="Close project tab"
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation()
                    closeProjectTab(id)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation()
                      closeProjectTab(id)
                    }
                  }}
                >
                  ×
                </span>
              </button>
            )
          })}
        </div>
        <div className="project-tabs-actions">
          <Dropdown
            isOpen={layoutOpen}
            onOpenChange={setLayoutOpen}
            onSelect={() => setLayoutOpen(false)}
            toggle={(toggleRef) => (
              <Button
                ref={toggleRef}
                className="pg-layout-menu"
                variant="plain"
                aria-label="Layout"
                title="Layout"
                aria-expanded={layoutOpen}
                onClick={() => setLayoutOpen((open) => !open)}
                icon={<SaveIcon />}
              />
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
          <Button
            className="pg-project-settings"
            variant="plain"
            aria-label="Project settings"
            title="Project settings"
            isDisabled={!currentProjectId}
            onClick={() => openProjectSettings(currentProjectId)}
            icon={<CogIcon />}
          />
          <Button
            className="pg-add-project"
            variant="plain"
            aria-label="Open project"
            title="Open project"
            onClick={() => setOpenProjectModal(true)}
            icon={<PlusIcon />}
          />
        </div>

        {menu ? (
          <div
            ref={menuRef}
            className="project-tab-context-menu"
            style={{ left: menu.x, top: menu.y }}
            role="menu"
          >
            <button
              type="button"
              role="menuitem"
              className="project-tab-context-item"
              onClick={() => {
                openProjectSettings(menu.projectId)
                setMenu(null)
              }}
            >
              Project settings…
            </button>
            <div className="project-tab-context-sep" role="separator" />
            <button
              type="button"
              role="menuitem"
              className="project-tab-context-item"
              onClick={() => {
                closeProjectTab(menu.projectId)
                setMenu(null)
              }}
            >
              Close tab
            </button>
          </div>
        ) : null}
      </div>

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
              No saved layouts yet. Use the save icon → Save layout…
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
