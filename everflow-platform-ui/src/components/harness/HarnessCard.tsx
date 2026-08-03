import { Label } from '@patternfly/react-core'
import { Link } from 'react-router-dom'
import {
  HARNESS_CATEGORY_LABELS,
  harnessLaunchCommand,
  type HarnessDef,
} from '@/data/harnesses'

interface HarnessCardProps {
  harness: HarnessDef
  usedByCount?: number
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export function HarnessCard({ harness, usedByCount }: HarnessCardProps) {
  const launch = harnessLaunchCommand(harness.id)
  const categoryLabel = HARNESS_CATEGORY_LABELS[harness.category]

  return (
    <article className="hn-card">
      <div className="hn-card-main">
        <span className={`hn-icon hn-icon--${harness.category}`} aria-hidden>
          {initials(harness.name)}
        </span>
        <div className="hn-card-body">
          <div className="hn-card-head">
            <h2 className="hn-card-title">{harness.name}</h2>
            <Label color="blue" isCompact>
              {categoryLabel}
            </Label>
          </div>
          <p className="hn-card-desc">{harness.description}</p>
          <div className="hn-card-meta">
            {launch ? (
              <code className="hn-card-cmd" title="CLI launch command inside the sandbox">
                {launch}
              </code>
            ) : (
              <span className="hn-card-kind">Sandbox install</span>
            )}
            {typeof usedByCount === 'number' && usedByCount > 0 ? (
              <Label color="grey" isCompact>
                Used by {usedByCount} project{usedByCount === 1 ? '' : 's'}
              </Label>
            ) : null}
          </div>
        </div>
      </div>
      <div className="hn-card-actions">
        <Link className="pf-v6-c-button pf-m-secondary pf-m-small" to="/">
          Open Playground
        </Link>
      </div>
    </article>
  )
}
