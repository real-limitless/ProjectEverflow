import {
  Button,
  EmptyState,
  EmptyStateActions,
  EmptyStateBody,
  EmptyStateFooter,
  EmptyStateVariant,
} from '@patternfly/react-core'
import CubesIcon from '@patternfly/react-icons/dist/esm/icons/cubes-icon'
import type { ComponentType, SVGProps } from 'react'

interface EmptySplashProps {
  title: string
  body: string
  primaryLabel?: string
  onPrimary?: () => void
  secondaryLabel?: string
  onSecondary?: () => void
  icon?: ComponentType<SVGProps<SVGSVGElement>>
  variant?: EmptyStateVariant
}

export function EmptySplash({
  title,
  body,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
  icon: Icon = CubesIcon,
  variant = EmptyStateVariant.sm,
}: EmptySplashProps) {
  return (
    <div className="studio-empty-splash">
      <EmptyState variant={variant} titleText={title} headingLevel="h3" icon={Icon}>
        <EmptyStateBody>{body}</EmptyStateBody>
        {(primaryLabel || secondaryLabel) && (
          <EmptyStateFooter>
            <EmptyStateActions>
              {primaryLabel && onPrimary && (
                <Button variant="primary" onClick={onPrimary}>
                  {primaryLabel}
                </Button>
              )}
              {secondaryLabel && onSecondary && (
                <Button variant="link" onClick={onSecondary}>
                  {secondaryLabel}
                </Button>
              )}
            </EmptyStateActions>
          </EmptyStateFooter>
        )}
      </EmptyState>
    </div>
  )
}
