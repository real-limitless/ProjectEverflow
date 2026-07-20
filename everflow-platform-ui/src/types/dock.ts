import type { PanelKey } from './panels'

export type DropEdge = 'left' | 'right' | 'top' | 'bottom' | 'center'

export interface GroupNode {
  type: 'group'
  id: string
  tabs: PanelKey[]
  active: PanelKey | null
}

export interface SplitNode {
  type: 'split'
  direction: 'horizontal' | 'vertical'
  sizes: number[]
  children: LayoutNode[]
}

export type LayoutNode = GroupNode | SplitNode

export interface GroupLocation {
  node: GroupNode
  parent: SplitNode | null
  index: number
}

export interface PanelLocation {
  group: GroupNode
  parent: SplitNode | null
  index: number
  tabIndex: number
}
