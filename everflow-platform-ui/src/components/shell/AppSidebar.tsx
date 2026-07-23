import {
  Badge,
  Button,
  Nav,
  NavItem,
  NavList,
  PageSidebar,
  PageSidebarBody,
} from '@patternfly/react-core'
import { NavLink, useLocation } from 'react-router-dom'
import { getPlaygroundFloatPalettePos } from '@/lib/palettePosition'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { NAV_ITEMS } from './navItems'

export function AppSidebar() {
  const location = useLocation()
  const isSidebarOpen = usePlaygroundStore((s) => s.isSidebarOpen)
  const paletteMode = usePlaygroundStore((s) => s.paletteMode)
  const paletteVisible = usePlaygroundStore((s) => s.paletteVisible)
  const paletteDragging = usePlaygroundStore((s) => s.paletteDragging)
  const setPaletteMode = usePlaygroundStore((s) => s.setPaletteMode)
  const setPaletteVisible = usePlaygroundStore((s) => s.setPaletteVisible)
  const setPalettePos = usePlaygroundStore((s) => s.setPalettePos)
  const slotEmpty = paletteMode !== 'docked' && !paletteDragging
  const trayHidden = paletteMode === 'chip' || !paletteVisible

  return (
    <PageSidebar id="sidebar" isSidebarOpen={isSidebarOpen}>
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
                  <NavItem
                    key={item.id}
                    itemId={item.id}
                    isActive={isActive}
                    className="pg-nav-item"
                  >
                    <NavLink
                      to={item.path}
                      title={item.label}
                      end={item.path === '/'}
                      className={({ isActive: routeActive }) =>
                        `pg-nav-link${routeActive || isActive ? ' is-active' : ''}`
                      }
                      aria-label={item.label}
                    >
                      <span className="pg-nav-icon" aria-hidden>
                        <Icon />
                      </span>
                      <span className="pf-v6-c-nav__link-text pg-nav-text">
                        {item.label}
                      </span>
                      {item.badge ? (
                        <Badge isRead={false} className="pg-nav-badge">
                          {item.badge}
                        </Badge>
                      ) : null}
                    </NavLink>
                  </NavItem>
                )
              })}
            </NavList>
          </Nav>
        </div>
        <div
          className={`nav-palette-slot${slotEmpty ? ' is-empty' : ''}${paletteDragging ? ' is-dragging-palette' : ''}`}
          id="navPaletteSlot"
          title="Drop panel tray here"
        >
          {paletteDragging ? (
            <div className="nav-palette-drop-hint" aria-hidden>
              Drop panel tray here
            </div>
          ) : null}
        </div>
        {trayHidden ? (
          <div className="pg-sidebar-footer">
            <Button
              className="pg-show-panels-btn"
              variant="secondary"
              size="sm"
              onClick={() => {
                // Bottom-center of playground so all panel type buttons are visible
                setPalettePos(getPlaygroundFloatPalettePos())
                setPaletteVisible(true)
                setPaletteMode('float')
              }}
              title="Show panel tray"
              aria-label="Show panel tray"
            >
              Panels
            </Button>
          </div>
        ) : null}
      </PageSidebarBody>
    </PageSidebar>
  )
}
