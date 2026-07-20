import { useEffect, useState } from 'react'
import { Label } from '@patternfly/react-core'
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function RepoStrip() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const setConnectRepoModal = usePlaygroundStore((s) => s.setConnectRepoModal)
  const project = PROJECTS[currentProjectId]
  const [activeRepo, setActiveRepo] = useState(
    project?.repos.find((r) => r.active)?.id || project?.repos[0]?.id || '',
  )

  useEffect(() => {
    const p = PROJECTS[currentProjectId]
    setActiveRepo(p?.repos.find((r) => r.active)?.id || p?.repos[0]?.id || '')
  }, [currentProjectId])

  if (!project) return null

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
