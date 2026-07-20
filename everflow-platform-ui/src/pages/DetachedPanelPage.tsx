import { useSearchParams } from 'react-router-dom'
import { PanelHost } from '@/components/workbench/PanelHost'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useEffect } from 'react'
import { PROJECTS } from '@/data/projects'
import type { PanelKey } from '@/types/panels'
import { typeOf } from '@/lib/panelIds'

export function DetachedPanelPage() {
  const [params] = useSearchParams()
  const panelId = (params.get('detach') || '') as PanelKey
  const projectId = params.get('project') || 'aura'
  const switchProject = usePlaygroundStore((s) => s.switchProject)
  const ensureInstanceState = usePlaygroundStore((s) => s.ensureInstanceState)

  useEffect(() => {
    if (PROJECTS[projectId]) switchProject(projectId)
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

  return (
    <div className="detached-panel-root">
      <PanelHost panelKey={panelId} />
    </div>
  )
}
