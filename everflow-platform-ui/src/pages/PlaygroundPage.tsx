import { ProjectTabBar } from '@/components/workbench/ProjectTabBar'
import { RepoStrip } from '@/components/workbench/RepoStrip'
import { DockRoot } from '@/components/workbench/DockRoot'

export function PlaygroundPage() {
  return (
    <div className="pg-main-workbench" id="main-content-playground">
      <ProjectTabBar />
      <RepoStrip />
      <div className="workspace">
        <DockRoot />
      </div>
    </div>
  )
}
