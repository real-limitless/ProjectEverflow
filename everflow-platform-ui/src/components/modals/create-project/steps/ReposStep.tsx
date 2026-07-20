import { Button, FormGroup, TextInput } from '@patternfly/react-core'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import TrashIcon from '@patternfly/react-icons/dist/esm/icons/trash-icon'
import type { ProjectRepo } from '@/types/project'
import { getTemplate, reposFromTemplate } from '@/data/projectTemplates'
import { slugifyProjectName } from '@/data/projects'
import type { WizardDraft } from '../types'

interface ReposStepProps {
  draft: WizardDraft
  onChange: (patch: Partial<WizardDraft>) => void
}

export function ReposStep({ draft, onChange }: ReposStepProps) {
  const repos = draft.repos

  const updateRepo = (index: number, patch: Partial<ProjectRepo>) => {
    const next = repos.map((r, i) => (i === index ? { ...r, ...patch } : r))
    onChange({ repos: next })
  }

  const removeRepo = (index: number) => {
    onChange({ repos: repos.filter((_, i) => i !== index) })
  }

  const addRepo = () => {
    const n = repos.length + 1
    onChange({
      repos: [
        ...repos,
        {
          id: `repo-${Date.now()}`,
          label: `repo-${n}`,
          active: repos.length === 0,
          url: '',
          branch: 'main',
          provider: 'github',
        },
      ],
    })
  }

  const applyTemplateDefaults = () => {
    const template = getTemplate(draft.templateId)
    const slug = slugifyProjectName(draft.slug || draft.name || 'project')
    onChange({ repos: reposFromTemplate(template, slug) })
  }

  return (
    <div className="create-wizard-repos">
      <p className="create-wizard-lead">
        Attach repositories for this project. They appear in the repo strip of the
        workbench. You can add more later.
      </p>
      <div className="create-wizard-repo-actions">
        <Button variant="secondary" size="sm" icon={<PlusIcon />} onClick={addRepo}>
          Add repository
        </Button>
        <Button variant="link" size="sm" onClick={applyTemplateDefaults}>
          Use template defaults
        </Button>
      </div>
      {repos.length === 0 ? (
        <p className="create-wizard-empty-hint">
          No repositories yet — optional for blank projects.
        </p>
      ) : (
        <ul className="create-wizard-repo-list">
          {repos.map((r, i) => (
            <li key={r.id} className="create-wizard-repo-row">
              <FormGroup label="Label" fieldId={`repo-label-${i}`}>
                <TextInput
                  id={`repo-label-${i}`}
                  value={r.label}
                  onChange={(_e, v) => updateRepo(i, { label: v })}
                  placeholder="org/app"
                />
              </FormGroup>
              <FormGroup label="URL" fieldId={`repo-url-${i}`}>
                <TextInput
                  id={`repo-url-${i}`}
                  value={r.url || ''}
                  onChange={(_e, v) => updateRepo(i, { url: v })}
                  placeholder="https://github.com/you/app.git"
                />
              </FormGroup>
              <FormGroup label="Branch" fieldId={`repo-branch-${i}`}>
                <TextInput
                  id={`repo-branch-${i}`}
                  value={r.branch || 'main'}
                  onChange={(_e, v) => updateRepo(i, { branch: v })}
                />
              </FormGroup>
              <label className="create-wizard-primary">
                <input
                  type="radio"
                  name="primary-repo"
                  checked={!!r.active}
                  onChange={() => {
                    onChange({
                      repos: repos.map((x, j) => ({
                        ...x,
                        active: j === i,
                      })),
                    })
                  }}
                />
                Primary
              </label>
              <Button
                variant="plain"
                aria-label="Remove repository"
                onClick={() => removeRepo(i)}
                icon={<TrashIcon />}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
