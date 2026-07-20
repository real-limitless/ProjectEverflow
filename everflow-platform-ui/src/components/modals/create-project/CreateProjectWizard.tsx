import { useMemo, useState } from 'react'
import {
  Wizard,
  WizardHeader,
  WizardStep,
  useWizardContext,
  Button,
  WizardFooterWrapper,
} from '@patternfly/react-core'
import type { ProjectTemplateId } from '@/data/projectTemplates'
import { slugifyProjectName } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'
import {
  applyTemplateToDraft,
  emptyWizardDraft,
  type WizardDraft,
} from './types'
import { BasicsStep, validateBasics } from './steps/BasicsStep'
import { TemplateStep } from './steps/TemplateStep'
import { ReposStep } from './steps/ReposStep'
import { HarnessesStep } from './steps/HarnessesStep'
import { OptionsStep } from './steps/OptionsStep'
import { ReviewStep } from './steps/ReviewStep'

interface CreateProjectWizardProps {
  onClose: () => void
}

function BasicsFooter({
  canNext,
  onClose,
}: {
  canNext: boolean
  onClose: () => void
}) {
  const { goToNextStep } = useWizardContext()
  return (
    <WizardFooterWrapper>
      <Button
        variant="primary"
        onClick={() => goToNextStep()}
        isDisabled={!canNext}
      >
        Next
      </Button>
      <Button variant="link" onClick={onClose}>
        Cancel
      </Button>
    </WizardFooterWrapper>
  )
}

export function CreateProjectWizard({ onClose }: CreateProjectWizardProps) {
  const createProject = usePlaygroundStore((s) => s.createProject)
  const [draft, setDraft] = useState<WizardDraft>(() => emptyWizardDraft())
  const [slugManual, setSlugManual] = useState(false)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)

  const patch = (p: Partial<WizardDraft>) => {
    setDraft((d) => ({ ...d, ...p }))
    if (error) setError('')
  }

  const onSelectTemplate = (templateId: ProjectTemplateId) => {
    setDraft((d) => applyTemplateToDraft(d, templateId))
  }

  const basicsOk = useMemo(() => validateBasics(draft), [draft])

  const finish = async () => {
    if (!validateBasics(draft)) {
      setError('Fix project name and slug before creating.')
      return
    }
    const payload: WizardDraft = {
      ...draft,
      slug: draft.slug || slugifyProjectName(draft.name),
      harnessIds:
        draft.harnessIds.length > 0
          ? draft.harnessIds
          : ['agent-claude-code', 'agent-opencode'],
    }
    setCreating(true)
    setError('')
    try {
      const id = await createProject(payload)
      if (!id) {
        setError('Could not create project. Try a different name or slug.')
        return
      }
      onClose()
    } finally {
      setCreating(false)
    }
  }

  return (
    <Wizard
      // Tall enough that Basics/Repos fields fit without a cramped scroll region
      height="min(78vh, 52rem)"
      isVisitRequired
      onClose={onClose}
      onSave={finish}
      header={
        <WizardHeader
          title="Create project"
          description="Name the project, pick a template, attach repos and harnesses."
          onClose={onClose}
          closeButtonAriaLabel="Close create project wizard"
        />
      }
      navAriaLabel="Create project steps"
    >
      <WizardStep
        id="basics"
        name="Basics"
        footer={<BasicsFooter canNext={basicsOk} onClose={onClose} />}
        status={draft.name && !basicsOk ? 'error' : 'default'}
      >
        <BasicsStep
          draft={draft}
          onChange={patch}
          slugManual={slugManual}
          setSlugManual={setSlugManual}
        />
      </WizardStep>
      <WizardStep id="template" name="Template">
        <TemplateStep draft={draft} onSelect={onSelectTemplate} />
      </WizardStep>
      <WizardStep id="repos" name="Repositories">
        <ReposStep draft={draft} onChange={patch} />
      </WizardStep>
      <WizardStep id="harnesses" name="Harnesses">
        <HarnessesStep draft={draft} onChange={patch} />
      </WizardStep>
      <WizardStep id="options" name="Options">
        <OptionsStep draft={draft} onChange={patch} />
      </WizardStep>
      <WizardStep
        id="review"
        name="Review"
        footer={{
          nextButtonText: creating ? 'Creating…' : 'Create project',
          isNextDisabled: creating,
        }}
      >
        <ReviewStep draft={draft} />
        {error ? (
          <p className="create-wizard-error" role="alert">
            {error}
          </p>
        ) : null}
      </WizardStep>
    </Wizard>
  )
}
