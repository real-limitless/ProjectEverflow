import { useEffect, useRef, useState } from 'react'
import { Button } from '@patternfly/react-core'
import CogIcon from '@patternfly/react-icons/dist/esm/icons/cog-icon'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import { PROJECTS, getProject } from '@/data/projects'
import { getSandboxStatus, isDemoMode } from '@/lib/api'
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

  const [menu, setMenu] = useState<ContextMenuState | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

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

  return (
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
  )
}
