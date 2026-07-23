import { Button } from '@patternfly/react-core'
import FolderOpenIcon from '@patternfly/react-icons/dist/esm/icons/folder-open-icon'
import PlusCircleIcon from '@patternfly/react-icons/dist/esm/icons/plus-circle-icon'
import { getProject, listVisibleProjectIds } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function ProjectEmptySplash() {
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const setCreateProjectModal = usePlaygroundStore((s) => s.setCreateProjectModal)
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)
  const openProject = usePlaygroundStore((s) => s.openProject)

  // catalogVersion forces re-read of mutable PROJECTS after create
  void catalogVersion
  const projectIds = listVisibleProjectIds()
  const hasProjects = projectIds.length > 0

  return (
    <div className="project-splash">
      <div className="project-splash-card">
        <div className="project-splash-icon" aria-hidden>
          <FolderOpenIcon />
        </div>
        <h1 className="project-splash-title">
          {hasProjects ? 'No project open' : 'Create your first project'}
        </h1>
        <p className="project-splash-desc">
          {hasProjects
            ? 'Open an existing project or create a new one to start building in the workbench.'
            : 'You do not have any projects yet. Create one to open the playground workbench.'}
        </p>
        <div className="project-splash-actions">
          <Button
            variant="primary"
            icon={<PlusCircleIcon />}
            onClick={() => setCreateProjectModal(true)}
          >
            Create project
          </Button>
          {hasProjects ? (
            <Button variant="secondary" onClick={() => setOpenProjectModal(true)}>
              Open project
            </Button>
          ) : null}
        </div>
        {hasProjects ? (
          <div className="project-splash-list">
            <div className="project-splash-list-label">Quick open</div>
            <div className="project-splash-chips">
              {projectIds.map((id) => {
                const p = getProject(id)
                if (!p) return null
                return (
                  <button
                    key={id}
                    type="button"
                    className="project-splash-chip"
                    onClick={() => openProject(id)}
                  >
                    <span className="dot" />
                    {p.name}
                  </button>
                )
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
