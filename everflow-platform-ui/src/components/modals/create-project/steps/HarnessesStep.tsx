import { HarnessPicker } from '@/components/project-settings/HarnessPicker'
import type { WizardDraft } from '../types'

interface HarnessesStepProps {
  draft: WizardDraft
  onChange: (patch: Partial<WizardDraft>) => void
}

export function HarnessesStep({ draft, onChange }: HarnessesStepProps) {
  return (
    <HarnessPicker
      idPrefix="create-harness"
      selectedIds={draft.harnessIds}
      onChange={(harnessIds) => onChange({ harnessIds })}
      lead={
        <>
          Harnesses run in the backend — CI, preview environments, databases, and AI
          sandbox tools. These are <strong>starting defaults</strong> only. After the
          project is created you can add, remove, or change harnesses anytime from{' '}
          <strong>Project settings</strong> (gear on the project bar, or right-click a
          project tab).
        </>
      }
    />
  )
}
