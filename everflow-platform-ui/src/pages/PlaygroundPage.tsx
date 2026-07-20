import { ProjectEmptySplash } from '@/components/workbench/ProjectEmptySplash'
import { ProjectTabBar } from '@/components/workbench/ProjectTabBar'
import { RepoStrip } from '@/components/workbench/RepoStrip'
import { DockRoot } from '@/components/workbench/DockRoot'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function PlaygroundPage() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)

  const hasOpenProject = Boolean(currentProjectId && openProjectIds.length > 0)

  if (!hasOpenProject) {
    return (
      <div className="pg-main-workbench pg-main-workbench--empty" id="main-content-playground">
        <ProjectEmptySplash />
      </div>
    )
  }

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
