import { ProjectEmptySplash } from '@/components/workbench/ProjectEmptySplash'
import { ProjectTabBar } from '@/components/workbench/ProjectTabBar'
import { RepoStrip } from '@/components/workbench/RepoStrip'
import { SandboxBootGate } from '@/components/workbench/SandboxBootGate'
import { DockRoot } from '@/components/workbench/DockRoot'
import { getProject } from '@/data/projects'
import { isSandboxWorkbenchReady } from '@/lib/sandboxReady'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function PlaygroundPage() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  void catalogVersion

  const hasOpenProject = Boolean(currentProjectId && openProjectIds.length > 0)
  const project = currentProjectId ? getProject(currentProjectId) : undefined
  const workbenchReady = isSandboxWorkbenchReady(project)

  if (!hasOpenProject || !currentProjectId) {
    return (
      <div className="pg-main-workbench pg-main-workbench--empty" id="main-content-playground">
        <ProjectEmptySplash />
      </div>
    )
  }

  // Sandbox-first: tab bar stays so users can switch/close; content is gated.
  if (!workbenchReady) {
    return (
      <div className="pg-main-workbench pg-main-workbench--booting" id="main-content-playground">
        <ProjectTabBar />
        <div className="pg-main-workbench--empty sandbox-boot-host">
          <SandboxBootGate projectId={currentProjectId} />
        </div>
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
