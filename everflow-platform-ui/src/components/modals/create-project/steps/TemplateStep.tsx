import {
  PROJECT_TEMPLATES,
  type ProjectTemplateId,
} from '@/data/projectTemplates'
import type { WizardDraft } from '../types'

interface TemplateStepProps {
  draft: WizardDraft
  onSelect: (templateId: ProjectTemplateId) => void
}

export function TemplateStep({ draft, onSelect }: TemplateStepProps) {
  return (
    <div className="create-wizard-templates">
      <p className="create-wizard-lead">
        Start from a template or a blank project. Templates pre-fill repos,
        harnesses, and starter files — you can change everything in later steps.
      </p>
      <div className="create-wizard-template-grid" role="listbox" aria-label="Project templates">
        {PROJECT_TEMPLATES.map((t) => {
          const selected = draft.templateId === t.id
          return (
            <button
              key={t.id}
              type="button"
              role="option"
              aria-selected={selected}
              className={`create-wizard-template-card${selected ? ' is-selected' : ''}`}
              onClick={() => onSelect(t.id)}
            >
              <span className="create-wizard-template-icon" aria-hidden>
                {t.icon}
              </span>
              <span className="create-wizard-template-name">{t.name}</span>
              <span className="create-wizard-template-desc">{t.description}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
