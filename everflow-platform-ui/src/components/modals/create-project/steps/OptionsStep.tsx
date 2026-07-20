import {
  Checkbox,
  Form,
  FormGroup,
  FormSelect,
  FormSelectOption,
} from '@patternfly/react-core'
import type { WizardDraft } from '../types'

interface OptionsStepProps {
  draft: WizardDraft
  onChange: (patch: Partial<WizardDraft>) => void
}

export function OptionsStep({ draft, onChange }: OptionsStepProps) {
  const opts = draft.options

  return (
    <Form className="create-wizard-form">
      <p className="create-wizard-lead">
        Optional defaults for the first workbench session. You can change these later in{' '}
        <strong>Project settings</strong>.
      </p>
      <FormGroup label="Default workspace layout" fieldId="cw-layout">
        <FormSelect
          id="cw-layout"
          value={opts.layout}
          onChange={(_e, v) =>
            onChange({
              options: {
                ...opts,
                layout: v as WizardDraft['options']['layout'],
              },
            })
          }
          aria-label="Workspace layout"
        >
          <FormSelectOption value="standard" label="Standard (chat + preview stack)" />
          <FormSelectOption value="chat-first" label="Chat-first" />
          <FormSelectOption value="code-first" label="Code-first" />
        </FormSelect>
      </FormGroup>
      <FormGroup label="Environment" fieldId="cw-env">
        <FormSelect
          id="cw-env"
          value={opts.environment}
          onChange={(_e, v) =>
            onChange({
              options: {
                ...opts,
                environment: v as WizardDraft['options']['environment'],
              },
            })
          }
          aria-label="Environment"
        >
          <FormSelectOption value="local" label="Local" />
          <FormSelectOption value="staging" label="Staging" />
          <FormSelectOption value="production-stub" label="Production (stub)" />
        </FormSelect>
      </FormGroup>
      <FormGroup label="Visibility" fieldId="cw-vis">
        <FormSelect
          id="cw-vis"
          value={opts.visibility}
          onChange={(_e, v) =>
            onChange({
              options: {
                ...opts,
                visibility: v as WizardDraft['options']['visibility'],
              },
            })
          }
          aria-label="Visibility"
        >
          <FormSelectOption value="private" label="Private (organization)" />
          <FormSelectOption value="public" label="Public" />
        </FormSelect>
      </FormGroup>
      <Checkbox
        id="cw-sample"
        label="Include sample chat, files, and terminal seed"
        isChecked={opts.includeSampleData}
        onChange={(_e, checked) =>
          onChange({ options: { ...opts, includeSampleData: checked } })
        }
      />
      <Checkbox
        id="cw-palette"
        label="Show panels tray after create"
        isChecked={opts.dockPalette}
        onChange={(_e, checked) =>
          onChange({ options: { ...opts, dockPalette: checked } })
        }
      />
    </Form>
  )
}
