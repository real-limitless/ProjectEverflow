import type { ReactNode } from 'react'
import type { LayoutNode, SplitNode } from '@/types/dock'
import { DockGroup } from './DockGroup'
import { DockSash } from './DockSash'

interface DockSplitProps {
  node: SplitNode
  path: number[]
  isRoot?: boolean
}

function renderNode(node: LayoutNode, path: number[], isRoot = false) {
  if (node.type === 'split') {
    return <DockSplit node={node} path={path} isRoot={isRoot} />
  }
  return <DockGroup node={node} />
}

export function DockSplit({ node, path, isRoot }: DockSplitProps) {
  const n = node.children.length
  const sizes = node.sizes?.length === n ? node.sizes : Array(n).fill(100 / n)

  // Flat structure: child, sash, child, sash, … — required for sash resize
  const items: ReactNode[] = []
  node.children.forEach((child, i) => {
    const size = sizes[i] ?? 100 / n
    items.push(
      <div
        key={`c-${i}`}
        className="dock-child"
        data-dock-index={i}
        style={
          node.direction === 'horizontal'
            ? { flex: `${size} 1 0`, width: 0, minWidth: 0 }
            : { flex: `${size} 1 0`, height: 0, minHeight: 0 }
        }
      >
        {renderNode(child, [...path, i])}
      </div>,
    )
    if (i < n - 1) {
      items.push(
        <DockSash
          key={`s-${i}`}
          direction={node.direction}
          sizes={sizes}
          sashIndex={i}
          pathToSplit={path}
        />,
      )
    }
  })

  return (
    <div
      className={`dock-split ${node.direction}`}
      style={isRoot ? { flex: 1, minHeight: 0, minWidth: 0 } : { minHeight: 0, minWidth: 0 }}
    >
      {items}
    </div>
  )
}

export function DockNode({
  node,
  path = [],
  isRoot = false,
}: {
  node: LayoutNode
  path?: number[]
  isRoot?: boolean
}) {
  return renderNode(node, path, isRoot)
}
