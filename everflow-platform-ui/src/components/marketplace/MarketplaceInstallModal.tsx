import {
  Button,
  Checkbox,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Spinner,
} from '@patternfly/react-core'
import { Link } from 'react-router-dom'
import type { MarketplaceItem, MarketplaceKind } from '@/data/marketplace'
import type { ApiProject } from '@/lib/api'

interface MarketplaceInstallModalProps {
  item: MarketplaceItem | null
  open: boolean
  onClose: () => void
  demoMode: boolean
  hasOrg: boolean
  projects: ApiProject[]
  projectsLoading: boolean
  selectedIds: Set<string>
  onToggleProject: (id: string, checked: boolean) => void
  installing: boolean
  onInstall: () => void
  installedByProject: Record<string, Set<string>>
  installedKey: (kind: MarketplaceKind, id: string) => string
  onOpenProjectModal: () => void
}

export function MarketplaceInstallModal({
  item,
  open,
  onClose,
  demoMode,
  hasOrg,
  projects,
  projectsLoading,
  selectedIds,
  onToggleProject,
  installing,
  onInstall,
  installedByProject,
  installedKey,
  onOpenProjectModal,
}: MarketplaceInstallModalProps) {
  return (
    <Modal
      isOpen={open && Boolean(item)}
      onClose={() => {
        if (!installing) onClose()
      }}
      variant={ModalVariant.medium}
      aria-labelledby="marketplace-install-title"
    >
      <ModalHeader
        title={item ? `Get “${item.name}”` : 'Add to projects'}
        labelId="marketplace-install-title"
        description={
          item?.kind === 'tool'
            ? 'Creates an HTTP tool on each selected project (sandbox not required).'
            : 'Requires a running sandbox. Writes into the project OpenCode harness.'
        }
      />
      <ModalBody>
        {demoMode || !hasOrg ? (
          <EmptyState
            variant={EmptyStateVariant.sm}
            titleText="Sign in to install"
            headingLevel="h3"
          >
            <EmptyStateBody>
              Marketplace install needs an authenticated org and project.{' '}
              <Button variant="link" isInline onClick={onOpenProjectModal}>
                Open a project
              </Button>{' '}
              from Playground after signing in.
            </EmptyStateBody>
          </EmptyState>
        ) : projectsLoading ? (
          <Spinner aria-label="Loading projects" />
        ) : projects.length === 0 ? (
          <EmptyState variant={EmptyStateVariant.sm} titleText="No projects" headingLevel="h3">
            <EmptyStateBody>
              Create or open a project first, then return here to install.
            </EmptyStateBody>
          </EmptyState>
        ) : (
          <ul className="marketplace-project-list">
            {projects.map((p) => {
              const running = p.sandbox_status === 'running'
              const toolOk = item?.kind === 'tool'
              const disabled = !toolOk && !running
              const key = item ? installedKey(item.kind, item.id) : ''
              const already = key ? installedByProject[p.id]?.has(key) : false
              return (
                <li key={p.id}>
                  <Checkbox
                    id={`mp-proj-${p.id}`}
                    label={
                      <span>
                        {p.name}{' '}
                        <Label isCompact color={running ? 'green' : 'grey'}>
                          {p.sandbox_status || 'unknown'}
                        </Label>
                        {already ? (
                          <Label isCompact color="blue" className="marketplace-installed-chip">
                            installed
                          </Label>
                        ) : null}
                      </span>
                    }
                    isChecked={selectedIds.has(p.id)}
                    isDisabled={disabled || installing}
                    onChange={(_e, checked) => onToggleProject(p.id, checked)}
                  />
                </li>
              )
            })}
          </ul>
        )}
      </ModalBody>
      <ModalFooter>
        <Button
          variant="primary"
          onClick={onInstall}
          isDisabled={installing || !selectedIds.size || demoMode || !hasOrg}
          isLoading={installing}
        >
          Install
        </Button>
        <Button variant="link" onClick={onClose} isDisabled={installing}>
          Cancel
        </Button>
        <Link className="pf-v6-c-button pf-m-secondary" to="/" aria-disabled={installing}>
          Open Playground
        </Link>
      </ModalFooter>
    </Modal>
  )
}
