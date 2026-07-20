import { Page } from '@patternfly/react-core'
import { Outlet, useLocation } from 'react-router-dom'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { OpenProjectModal } from '@/components/modals/OpenProjectModal'
import { ConnectRepoModal } from '@/components/modals/ConnectRepoModal'
import { PanelPalette } from '@/components/palette/PanelPalette'
import { AppMasthead } from './AppMasthead'
import { AppSidebar } from './AppSidebar'

interface AppShellProps {
  detached?: boolean
}

export function AppShell({ detached = false }: AppShellProps) {
  const location = useLocation()
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)

  const isPlayground =
    location.pathname === '/' || location.pathname === ''

  if (detached) {
    return (
      <div className="detached-shell">
        <Outlet />
      </div>
    )
  }

  return (
    <>
      <Page
        className={`pg-shell ${isPlayground ? 'pg-shell--playground' : 'pg-shell--standard'}`}
        masthead={<AppMasthead />}
        sidebar={<AppSidebar />}
        mainContainerId="main-content"
        data-sidebar-open={isSidebarOpen ? 'true' : 'false'}
      >
        <Outlet />
      </Page>
      {isPlayground ? <PanelPalette /> : null}
      <OpenProjectModal />
      <ConnectRepoModal />
    </>
  )
}
