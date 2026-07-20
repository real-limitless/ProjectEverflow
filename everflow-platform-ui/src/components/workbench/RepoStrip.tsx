import { Label } from '@patternfly/react-core'
import { useState } from 'react'
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function RepoStrip() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const setConnectRepoModal = usePlaygroundStore((s) => s.setConnectRepoModal)
  const project = PROJECTS[currentProjectId]
  const [activeRepo, setActiveRepo] = useState(
    project?.repos.find((r) => r.active)?.id || project?.repos[0]?.id || '',
  )

  if (!project) return null

  return (
    <div className="repo-strip" id="repoStrip">
      {project.repos.map((r) => (
        <button
          key={r.id}
          type="button"
          className="repo-chip"
          onClick={() => setActiveRepo(r.id)}
        >
          <Label color={r.id === activeRepo ? 'blue' : 'grey'} variant="outline">
            <span className="status" />
            {r.label}
          </Label>
        </button>
      ))}
      <button
        type="button"
        className="repo-chip"
        onClick={() => setConnectRepoModal(true)}
      >
        <Label color="grey" variant="outline">
          + Connect
        </Label>
      </button>
    </div>
  )
}
