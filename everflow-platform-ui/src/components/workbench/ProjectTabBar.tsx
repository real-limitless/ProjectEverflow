import { Button } from '@patternfly/react-core'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function ProjectTabBar() {
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const switchProject = usePlaygroundStore((s) => s.switchProject)
  const closeProjectTab = usePlaygroundStore((s) => s.closeProjectTab)
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)

  return (
    <div className="pg-project-bar">
      <div className="project-tabs" id="projectTabs">
        {openProjectIds.map((id) => {
          const p = PROJECTS[id]
          if (!p) return null
          return (
            <button
              key={id}
              type="button"
              className={`project-tab${id === currentProjectId ? ' active' : ''}`}
              onClick={() => switchProject(id)}
            >
              <span className="dot" />
              <span className="pt-name">{p.name}</span>
              <span
                className="pt-close"
                title="Close project tab"
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation()
                  closeProjectTab(id)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.stopPropagation()
                    closeProjectTab(id)
                  }
                }}
              >
                ×
              </span>
            </button>
          )
        })}
      </div>
      <div className="project-tabs-actions">
        <Button
          className="pg-add-project"
          variant="plain"
          aria-label="Open project"
          title="Open project"
          onClick={() => setOpenProjectModal(true)}
          icon={<PlusIcon />}
        />
      </div>
    </div>
  )
}
