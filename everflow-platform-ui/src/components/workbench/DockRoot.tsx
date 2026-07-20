import { usePlaygroundStore } from '@/store/playgroundStore'
import { DockNode } from './DockSplit'

export function DockRoot() {
  const layout = usePlaygroundStore((s) => s.layout)

  return (
    <div className="dock-root" id="dockRoot">
      <DockNode node={layout} path={[]} isRoot />
    </div>
  )
}
