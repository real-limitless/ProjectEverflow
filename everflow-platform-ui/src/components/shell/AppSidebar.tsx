import {
  Badge,
  Button,
  Nav,
  NavItem,
  NavList,
  PageSidebar,
  PageSidebarBody,
} from '@patternfly/react-core'
import AngleLeftIcon from '@patternfly/react-icons/dist/esm/icons/angle-left-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import { NavLink, useLocation } from 'react-router-dom'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { NAV_ITEMS } from './navItems'

export function AppSidebar() {
  const location = useLocation()
  const sidebarCollapsed = usePlaygroundStore((s) => s.sidebarCollapsed)
  const setSidebarCollapsed = usePlaygroundStore((s) => s.setSidebarCollapsed)
  const paletteMode = usePlaygroundStore((s) => s.paletteMode)

  return (
    <PageSidebar id="sidebar">
      <PageSidebarBody className="pg-sidebar-body-flex">
        <div className="pg-nav-wrap">
          <Nav className="pg-nav" aria-label="Global">
            <NavList>
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon
                const isActive =
                  item.path === '/'
                    ? location.pathname === '/' || location.pathname === ''
                    : location.pathname.startsWith(item.path)
                return (
                  <NavItem key={item.id} itemId={item.id} isActive={isActive}>
                    <NavLink to={item.path} title={item.label}>
                      <span className="pf-v6-c-nav__link-icon">
                        <Icon />
                      </span>
                      <span className="pf-v6-c-nav__link-text">{item.label}</span>
                      {item.badge ? (
                        <Badge isRead={false}>{item.badge}</Badge>
                      ) : null}
                    </NavLink>
                  </NavItem>
                )
              })}
            </NavList>
          </Nav>
        </div>
        <div
          className={`nav-palette-slot${paletteMode === 'docked' ? '' : ' is-empty'}`}
          id="navPaletteSlot"
          title="Dock panel tray here"
        />
        <div className="pg-sidebar-footer">
          <Button
            className="pg-collapse-btn"
            variant="plain"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? <AngleRightIcon /> : <AngleLeftIcon />}
            <span className="pg-collapse-label">
              {sidebarCollapsed ? 'Expand' : 'Collapse'}
            </span>
          </Button>
        </div>
      </PageSidebarBody>
    </PageSidebar>
  )
}
