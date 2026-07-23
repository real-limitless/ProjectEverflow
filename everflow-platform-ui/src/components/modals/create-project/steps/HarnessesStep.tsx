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
          Harnesses run in the sandbox — agent CLIs, Postgres tools, and related
          installers. Your selection is applied when the sandbox is provisioned. After
          create, change them anytime in <strong>Project settings</strong>; saving
          reconfigures or recreates the sandbox.
        </>
      }
    />
  )
}
