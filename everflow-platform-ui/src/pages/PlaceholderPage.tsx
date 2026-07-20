import {
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  PageSection,
} from '@patternfly/react-core'
import CubesIcon from '@patternfly/react-icons/dist/esm/icons/cubes-icon'

interface PlaceholderPageProps {
  title: string
  description?: string
}

export function PlaceholderPage({
  title,
  description = 'Coming soon — this surface will plug into the Everflow platform API.',
}: PlaceholderPageProps) {
  return (
    <>
      <PageSection aria-labelledby="page-title">
        <Content>
          <h1 id="page-title">{title}</h1>
          <p>{description}</p>
        </Content>
      </PageSection>
      <PageSection isFilled aria-label={`${title} content`}>
        <EmptyState
          variant={EmptyStateVariant.lg}
          titleText="Nothing here yet"
          headingLevel="h2"
          icon={CubesIcon}
          isFullHeight
        >
          <EmptyStateBody>
            This area will host {title.toLowerCase()} once the platform API is
            connected. Use <strong>Playground v2</strong> in the nav for the IDE
            workbench.
          </EmptyStateBody>
        </EmptyState>
      </PageSection>
    </>
  )
}
