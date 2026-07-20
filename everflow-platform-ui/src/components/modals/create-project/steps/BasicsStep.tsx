import { Form, FormGroup, TextArea, TextInput } from '@patternfly/react-core'
import { isSlugTaken } from '@/data/createProjectDraft'
import { slugifyProjectName } from '@/data/projects'
import type { WizardDraft } from '../types'

interface BasicsStepProps {
  draft: WizardDraft
  onChange: (patch: Partial<WizardDraft>) => void
  slugManual: boolean
  setSlugManual: (v: boolean) => void
}

export function BasicsStep({
  draft,
  onChange,
  slugManual,
  setSlugManual,
}: BasicsStepProps) {
  const slug = draft.slug || ''
  const slugError =
    slug && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)
      ? 'Use lowercase letters, numbers, and hyphens only'
      : slug && isSlugTaken(slug)
        ? 'This slug is already in use'
        : ''

  return (
    <Form className="create-wizard-form">
      <FormGroup label="Project name" isRequired fieldId="cw-name">
        <TextInput
          id="cw-name"
          value={draft.name}
          onChange={(_e, v) => {
            const patch: Partial<WizardDraft> = { name: v }
            if (!slugManual) patch.slug = slugifyProjectName(v)
            onChange(patch)
          }}
          placeholder="e.g. Aura Host"
          autoFocus
        />
      </FormGroup>
      <FormGroup label="Description" fieldId="cw-desc">
        <TextArea
          id="cw-desc"
          value={draft.description || ''}
          onChange={(_e, v) => onChange({ description: v })}
          placeholder="What is this project for?"
          rows={3}
        />
      </FormGroup>
      <FormGroup label="Project slug" fieldId="cw-slug">
        <TextInput
          id="cw-slug"
          value={slug}
          onChange={(_e, v) => {
            setSlugManual(true)
            onChange({ slug: v.toLowerCase().replace(/[^a-z0-9-]/g, '-') })
          }}
          placeholder="my-project"
          validated={slugError ? 'error' : 'default'}
        />
        <div
          className={`create-wizard-help${slugError ? ' is-error' : ''}`}
          style={{ marginTop: 6, fontSize: '0.85rem' }}
        >
          {slugError || 'Used in URLs and sandbox paths'}
        </div>
      </FormGroup>
    </Form>
  )
}

export function validateBasics(draft: WizardDraft): boolean {
  if (!draft.name.trim()) return false
  const slug = (draft.slug || slugifyProjectName(draft.name)).trim()
  if (!slug || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) return false
  if (isSlugTaken(slug)) return false
  return true
}
