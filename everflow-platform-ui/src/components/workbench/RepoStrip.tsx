import { Label } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function RepoStrip() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const activeRepoByProject = usePlaygroundStore((s) => s.activeRepoByProject)
  const setActiveRepo = usePlaygroundStore((s) => s.setActiveRepo)
  const setConnectRepoModal = usePlaygroundStore((s) => s.setConnectRepoModal)
  const getActiveRepoId = usePlaygroundStore((s) => s.getActiveRepoId)

  void catalogVersion
  void activeRepoByProject

  const project = getProject(currentProjectId)
  if (!project) return null

  const activeRepo = getActiveRepoId(currentProjectId)

  return (
    <div className="repo-strip repo-strip--surface" id="repoStrip">
      <span className="repo-strip-label">Repos</span>
      {project.repos.map((r) => {
        const active = r.id === activeRepo
        return (
          <button
            key={r.id}
            type="button"
            className={`repo-chip${active ? ' is-active' : ''}`}
            onClick={() => setActiveRepo(r.id)}
          >
            <Label color={active ? 'blue' : 'grey'} variant={active ? 'filled' : 'outline'}>
              <span className="status" />
              {r.label}
            </Label>
          </button>
        )
      })}
      <button
        type="button"
        className="repo-chip"
        onClick={() => setConnectRepoModal(true)}
      >
        <Label color="blue" variant="outline">
          + Connect
        </Label>
      </button>
    </div>
  )
}
