import { useEffect } from 'react'
import { Page, Spinner } from '@patternfly/react-core'
import { Outlet, useLocation } from 'react-router-dom'
import { getProject } from '@/data/projects'
import { isSandboxWorkbenchReady } from '@/lib/sandboxReady'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useAuthStore } from '@/store/authStore'
import { CreateProjectModal } from '@/components/modals/CreateProjectModal'
import { OpenProjectModal } from '@/components/modals/OpenProjectModal'
import { ConnectRepoModal } from '@/components/modals/ConnectRepoModal'
import { ProjectSettingsModal } from '@/components/modals/ProjectSettingsModal'
import { LoginModal } from '@/components/auth/LoginModal'
import { PanelPalette } from '@/components/palette/PanelPalette'
import { AppMasthead } from './AppMasthead'
import { AppSidebar } from './AppSidebar'

interface AppShellProps {
  detached?: boolean
}

export function AppShell({ detached = false }: AppShellProps) {
  const location = useLocation()
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const ready = useAuthStore((s) => s.ready)
  const bootstrap = useAuthStore((s) => s.bootstrap)
  const user = useAuthStore((s) => s.user)
  const demoMode = useAuthStore((s) => s.demoMode)
  void catalogVersion

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  const isPlayground =
    location.pathname === '/' || location.pathname === ''
  const hasOpenProject = Boolean(currentProjectId && openProjectIds.length > 0)
  const currentProject = currentProjectId ? getProject(currentProjectId) : undefined
  const workbenchReady = hasOpenProject && isSandboxWorkbenchReady(currentProject)

  if (detached) {
    return (
      <div className="detached-shell">
        <Outlet />
      </div>
    )
  }

  if (!ready) {
    return (
      <div className="auth-boot-splash">
        <Spinner size="xl" aria-label="Loading Everflow" />
      </div>
    )
  }

  const blocked = !demoMode && !user

  return (
    <>
      <Page
        className={`pg-shell ${isPlayground ? 'pg-shell--playground' : 'pg-shell--standard'}`}
        masthead={<AppMasthead />}
        sidebar={blocked ? undefined : <AppSidebar />}
        mainContainerId="main-content"
        data-sidebar-open={isSidebarOpen ? 'true' : 'false'}
      >
        {blocked ? (
          <div className="auth-boot-splash">
            <p>Sign in to open projects and sandboxes.</p>
          </div>
        ) : (
          <Outlet />
        )}
      </Page>
      {!blocked && isPlayground && workbenchReady ? <PanelPalette /> : null}
      {!blocked ? (
        <>
          <OpenProjectModal />
          <CreateProjectModal />
          <ConnectRepoModal />
          <ProjectSettingsModal />
        </>
      ) : null}
      <LoginModal />
    </>
  )
}
