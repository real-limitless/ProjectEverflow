import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PanelHost } from '@/components/workbench/PanelHost'
import { SandboxBootGate } from '@/components/workbench/SandboxBootGate'
import { PROJECTS, getProject } from '@/data/projects'
import { isSandboxWorkbenchReady } from '@/lib/sandboxReady'
import { typeOf } from '@/lib/panelIds'
import type { PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function DetachedPanelPage() {
  const [params] = useSearchParams()
  const panelId = (params.get('detach') || '') as PanelKey
  const projectId = params.get('project') || ''
  const switchProject = usePlaygroundStore((s) => s.switchProject)
  const ensureInstanceState = usePlaygroundStore((s) => s.ensureInstanceState)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const sandboxVerified = usePlaygroundStore((s) =>
    projectId ? Boolean(s.sandboxReadyByProject[projectId]) : false,
  )
  void catalogVersion

  useEffect(() => {
    if (projectId && PROJECTS[projectId]) switchProject(projectId)
    if (panelId) {
      const t = typeOf(panelId)
      if (t) ensureInstanceState(panelId, { type: t })
    }
    document.body.classList.add('detached-mode')
    return () => document.body.classList.remove('detached-mode')
  }, [panelId, projectId, switchProject, ensureInstanceState])

  if (!panelId) {
    return <div className="empty-group">No panel specified</div>
  }

  const project = projectId ? getProject(projectId) : undefined
  const workbenchReady = isSandboxWorkbenchReady(project, sandboxVerified)

  if (projectId && project?.fromApi && !workbenchReady) {
    return (
      <div className="detached-panel-root detached-panel-root--booting">
        <SandboxBootGate projectId={projectId} />
      </div>
    )
  }

  return (
    <div className="detached-panel-root">
      <PanelHost panelKey={panelId} />
    </div>
  )
}
