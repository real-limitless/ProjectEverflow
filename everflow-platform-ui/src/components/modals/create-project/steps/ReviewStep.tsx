import { DescriptionList, DescriptionListDescription, DescriptionListGroup, DescriptionListTerm } from '@patternfly/react-core'
import { getHarness } from '@/data/harnesses'
import { getTemplate } from '@/data/projectTemplates'
import type { WizardDraft } from '../types'

interface ReviewStepProps {
  draft: WizardDraft
}

export function ReviewStep({ draft }: ReviewStepProps) {
  const template = getTemplate(draft.templateId)
  const harnessNames = draft.harnessIds
    .map((id) => getHarness(id)?.name || id)
    .join(', ')

  return (
    <div className="create-wizard-review">
      <p className="create-wizard-lead">
        Confirm the project configuration, then create it.
      </p>
      <DescriptionList isHorizontal isCompact>
        <DescriptionListGroup>
          <DescriptionListTerm>Name</DescriptionListTerm>
          <DescriptionListDescription>{draft.name || '—'}</DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Slug</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.slug || '—'}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Description</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.description?.trim() || '—'}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Template</DescriptionListTerm>
          <DescriptionListDescription>
            {template.icon} {template.name}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Repositories</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.repos.length
              ? draft.repos
                  .map((r) => `${r.label}${r.active ? ' (primary)' : ''}`)
                  .join(', ')
              : 'None'}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Harnesses</DescriptionListTerm>
          <DescriptionListDescription>
            {harnessNames || 'None'}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Layout</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.options.layout}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Environment</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.options.environment}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Visibility</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.options.visibility}
          </DescriptionListDescription>
        </DescriptionListGroup>
        <DescriptionListGroup>
          <DescriptionListTerm>Sample data</DescriptionListTerm>
          <DescriptionListDescription>
            {draft.options.includeSampleData ? 'Yes' : 'No'}
          </DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </div>
  )
}
