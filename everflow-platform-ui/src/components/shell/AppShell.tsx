import { Page } from '@patternfly/react-core'
import { Outlet } from 'react-router-dom'
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
  const sidebarCollapsed = usePlaygroundStore((s) => s.sidebarCollapsed)

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
        className="pg-shell"
        masthead={<AppMasthead />}
        sidebar={<AppSidebar />}
        isManagedSidebar
        data-collapsed={sidebarCollapsed ? 'true' : 'false'}
      >
        <Outlet />
      </Page>
      <PanelPalette />
      <OpenProjectModal />
      <ConnectRepoModal />
    </>
  )
}
