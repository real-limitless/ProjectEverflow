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
  return (
    <div
      className={`dock-split ${node.direction}`}
      style={isRoot ? { flex: 1 } : undefined}
    >
      {node.children.map((child, i) => {
        const size = node.sizes?.[i] ?? 100 / n
        return (
          <div key={i} style={{ display: 'contents' }}>
            <div
              className="dock-child"
              style={
                node.direction === 'horizontal'
                  ? { flex: `${size} 1 0`, width: 0 }
                  : { flex: `${size} 1 0`, height: 0 }
              }
            >
              {renderNode(child, [...path, i])}
            </div>
            {i < n - 1 ? (
              <DockSash
                direction={node.direction}
                sizes={node.sizes}
                sashIndex={i}
                pathToSplit={path}
              />
            ) : null}
          </div>
        )
      })}
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
