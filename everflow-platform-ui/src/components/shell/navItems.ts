import type { ComponentType, SVGProps } from 'react'
import TachometerAltIcon from '@patternfly/react-icons/dist/esm/icons/tachometer-alt-icon'
import ChartLineIcon from '@patternfly/react-icons/dist/esm/icons/chart-line-icon'
import CommentsIcon from '@patternfly/react-icons/dist/esm/icons/comments-icon'
import CreditCardIcon from '@patternfly/react-icons/dist/esm/icons/credit-card-icon'
import CubeIcon from '@patternfly/react-icons/dist/esm/icons/cube-icon'

export interface NavItemDef {
  id: string
  label: string
  path: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  badge?: string
}

export const NAV_ITEMS: NavItemDef[] = [
  { id: 'overview', label: 'Overview', path: '/overview', icon: TachometerAltIcon },
  { id: 'usage', label: 'Usage', path: '/usage', icon: ChartLineIcon },
  {
    id: 'playground',
    label: 'Playground v2',
    path: '/',
    icon: CommentsIcon,
    badge: 'NEW',
  },
  { id: 'plans', label: 'Plans & Billing', path: '/plans', icon: CreditCardIcon },
  { id: 'harnesses', label: 'Harnesses', path: '/harnesses', icon: CubeIcon },
]
