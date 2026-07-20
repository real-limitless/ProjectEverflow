import {
  EmptyState,
  EmptyStateBody,
  PageSection,
  Title,
} from '@patternfly/react-core'

interface PlaceholderPageProps {
  title: string
  description?: string
}

export function PlaceholderPage({
  title,
  description = 'Coming soon — this surface will plug into the Everflow platform API.',
}: PlaceholderPageProps) {
  return (
    <PageSection>
      <EmptyState>
        <Title headingLevel="h1" size="lg">
          {title}
        </Title>
        <EmptyStateBody>{description}</EmptyStateBody>
      </EmptyState>
    </PageSection>
  )
}
