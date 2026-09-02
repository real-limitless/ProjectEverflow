import type { ComponentType, SVGProps } from 'react'
import ChartLineIcon from '@patternfly/react-icons/dist/esm/icons/chart-line-icon'
import CommentsIcon from '@patternfly/react-icons/dist/esm/icons/comments-icon'
import CubeIcon from '@patternfly/react-icons/dist/esm/icons/cube-icon'
import CatalogIcon from '@patternfly/react-icons/dist/esm/icons/catalog-icon'

export interface NavItemDef {
  id: string
  label: string
  path: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  badge?: string
}

export const NAV_ITEMS: NavItemDef[] = [
  { id: 'usage', label: 'Usage', path: '/usage', icon: ChartLineIcon },
  {
    id: 'playground',
    label: 'Playground v2',
    path: '/',
    icon: CommentsIcon,
    badge: 'NEW',
  },
  { id: 'marketplace', label: 'Marketplace', path: '/marketplace', icon: CatalogIcon },
  { id: 'harnesses', label: 'Harnesses', path: '/harnesses', icon: CubeIcon },
]
