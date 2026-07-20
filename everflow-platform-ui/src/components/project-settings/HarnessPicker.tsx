import type { ReactNode } from 'react'
import { Checkbox } from '@patternfly/react-core'
import { HARNESS_CATALOG } from '@/data/harnesses'

interface HarnessPickerProps {
  selectedIds: string[]
  onChange: (ids: string[]) => void
  /** Optional lead / help text above the list */
  lead?: ReactNode
  idPrefix?: string
}

/** Full catalog checkbox list — used by create wizard and Project settings. */
export function HarnessPicker({
  selectedIds,
  onChange,
  lead,
  idPrefix = 'harness',
}: HarnessPickerProps) {
  const selected = new Set(selectedIds)

  const toggle = (id: string, checked: boolean) => {
    const next = checked
      ? [...selectedIds, id]
      : selectedIds.filter((x) => x !== id)
    onChange(next)
  }

  return (
    <div className="create-wizard-harnesses harness-picker">
      {lead ? <div className="create-wizard-lead">{lead}</div> : null}
      <ul className="create-wizard-harness-list">
        {HARNESS_CATALOG.map((h) => (
          <li key={h.id} className="create-wizard-harness-item">
            <Checkbox
              id={`${idPrefix}-${h.id}`}
              label={
                <span className="create-wizard-harness-label">
                  <strong>{h.name}</strong>
                  <span className="create-wizard-harness-meta">{h.category}</span>
                </span>
              }
              description={h.description}
              isChecked={selected.has(h.id)}
              onChange={(_e, checked) => toggle(h.id, checked)}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}
