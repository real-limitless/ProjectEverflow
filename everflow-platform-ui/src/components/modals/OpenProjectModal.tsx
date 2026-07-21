import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateFooter,
  EmptyStateVariant,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  SearchInput,
  Spinner,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import CubesIcon from '@patternfly/react-icons/dist/esm/icons/cubes-icon'
import FolderOpenIcon from '@patternfly/react-icons/dist/esm/icons/folder-open-icon'
import PlusCircleIcon from '@patternfly/react-icons/dist/esm/icons/plus-circle-icon'
import SearchIcon from '@patternfly/react-icons/dist/esm/icons/search-icon'
import { getProject, listProjectIds } from '@/data/projects'
import { getTemplate } from '@/data/projectTemplates'
import { isDemoMode, listProjects } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { usePlaygroundStore } from '@/store/playgroundStore'

type FilterMode = 'all' | 'open' | 'available'

interface ProjectRow {
  id: string
  name: string
  slug: string
  description: string
  templateLabel: string
  templateIcon: string
  repoCount: number
  harnessCount: number
  isOpen: boolean
  isActive: boolean
  sandboxStatus?: string
  fromApi?: boolean
}

export function OpenProjectModal() {
  const isOpen = usePlaygroundStore((s) => s.openProjectModal)
  const setOpen = usePlaygroundStore((s) => s.setOpenProjectModal)
  const setCreate = usePlaygroundStore((s) => s.setCreateProjectModal)
  const openProject = usePlaygroundStore((s) => s.openProject)
  const ingestApiProject = usePlaygroundStore((s) => s.ingestApiProject)
  const openProjectIds = usePlaygroundStore((s) => s.openProjectIds)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const org = useAuthStore((s) => s.org)
  const user = useAuthStore((s) => s.user)
  void catalogVersion

  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterMode>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loadingApi, setLoadingApi] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    setQuery('')
    setFilter('all')
    setSelectedId(null)
    setApiError(null)

    if (isDemoMode() || !user || !org) return

    let cancelled = false
    setLoadingApi(true)
    void listProjects(org.id)
      .then((projects) => {
        if (cancelled) return
        for (const ap of projects) {
          ingestApiProject(ap)
        }
      })
      .catch((e) => {
        if (!cancelled) setApiError(e instanceof Error ? e.message : 'Failed to load projects')
      })
      .finally(() => {
        if (!cancelled) setLoadingApi(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, user, org, ingestApiProject])

  const rows = useMemo((): ProjectRow[] => {
    return listProjectIds()
      .map((id) => {
        const p = getProject(id)
        if (!p) return null
        // In API mode hide pure demo seeds unless already open
        if (!isDemoMode() && user && !p.fromApi && !openProjectIds.includes(id)) {
          return null
        }
        const template = getTemplate(p.templateId)
        return {
          id,
          name: p.name,
          slug: p.slug || id,
          description: p.description?.trim() || '',
          templateLabel: template.name,
          templateIcon: template.icon,
          repoCount: p.repos?.length ?? 0,
          harnessCount: p.harnesses?.filter((h) => h.enabled).length ?? 0,
          isOpen: openProjectIds.includes(id),
          isActive: currentProjectId === id,
          sandboxStatus: p.sandboxStatus,
          fromApi: p.fromApi,
        } satisfies ProjectRow
      })
      .filter(Boolean)
      .sort((a, b) => a!.name.localeCompare(b!.name)) as ProjectRow[]
  }, [catalogVersion, openProjectIds, currentProjectId, user])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows.filter((r) => {
      if (filter === 'open' && !r.isOpen) return false
      if (filter === 'available' && r.isOpen) return false
      if (!q) return true
      return (
        r.name.toLowerCase().includes(q) ||
        r.slug.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.templateLabel.toLowerCase().includes(q) ||
        r.id.toLowerCase().includes(q)
      )
    })
  }, [rows, query, filter])

  const selected =
    filtered.find((r) => r.id === selectedId) ||
    filtered.find((r) => r.isActive) ||
    filtered[0] ||
    null

  useEffect(() => {
    if (!selected) {
      setSelectedId(null)
      return
    }
    if (selectedId !== selected.id) setSelectedId(selected.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered])

  const openSelected = () => {
    if (!selected) return
    openProject(selected.id)
  }

  const goCreate = () => {
    setOpen(false)
    setCreate(true)
  }

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen}
      onClose={() => setOpen(false)}
      aria-labelledby="openProjectModalTitle"
      className="open-project-modal"
    >
      <ModalHeader
        title="Open project"
        labelId="openProjectModalTitle"
        description="Browse your projects, search, and open one in the workbench."
      />
      <ModalBody>
        {loadingApi ? (
          <div className="open-project-loading">
            <Spinner size="lg" aria-label="Loading projects" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            variant={EmptyStateVariant.sm}
            titleText="No projects yet"
            headingLevel="h2"
            icon={CubesIcon}
          >
            <EmptyStateBody>
              {apiError
                ? apiError
                : 'Create a project to get started with the playground workbench.'}
            </EmptyStateBody>
            <EmptyStateFooter>
              <Button variant="primary" icon={<PlusCircleIcon />} onClick={goCreate}>
                Create project
              </Button>
            </EmptyStateFooter>
          </EmptyState>
        ) : (
          <div className="open-project-browser">
            <div className="open-project-toolbar">
              <SearchInput
                className="open-project-search"
                placeholder="Search by name, slug, or template…"
                value={query}
                onChange={(_e, v) => setQuery(v)}
                onClear={() => setQuery('')}
                aria-label="Search projects"
              />
              <ToggleGroup aria-label="Filter projects" className="open-project-filters">
                <ToggleGroupItem
                  text={`All (${rows.length})`}
                  isSelected={filter === 'all'}
                  onChange={() => setFilter('all')}
                />
                <ToggleGroupItem
                  text={`Open (${rows.filter((r) => r.isOpen).length})`}
                  isSelected={filter === 'open'}
                  onChange={() => setFilter('open')}
                />
                <ToggleGroupItem
                  text={`Available (${rows.filter((r) => !r.isOpen).length})`}
                  isSelected={filter === 'available'}
                  onChange={() => setFilter('available')}
                />
              </ToggleGroup>
            </div>

            <div className="open-project-meta">
              <span>
                {filtered.length} project{filtered.length === 1 ? '' : 's'}
                {query.trim() ? ` matching “${query.trim()}”` : ''}
              </span>
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                variant={EmptyStateVariant.xs}
                className="open-project-empty-filter"
                titleText="No matches"
                headingLevel="h3"
                icon={SearchIcon}
              >
                <EmptyStateBody>
                  Try a different search or filter, or create a new project.
                </EmptyStateBody>
              </EmptyState>
            ) : (
              <div className="open-project-list" role="listbox" aria-label="Projects">
                {filtered.map((r) => {
                  const isSelected = selected?.id === r.id
                  return (
                    <button
                      key={r.id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`open-project-row${isSelected ? ' is-selected' : ''}${r.isActive ? ' is-active' : ''}`}
                      onClick={() => setSelectedId(r.id)}
                      onDoubleClick={() => openProject(r.id)}
                    >
                      <span className="open-project-row-icon" aria-hidden>
                        <FolderOpenIcon />
                      </span>
                      <span className="open-project-row-main">
                        <span className="open-project-row-title">
                          <span className="open-project-row-name">{r.name}</span>
                          {r.isActive ? (
                            <Label color="blue" isCompact>
                              Active
                            </Label>
                          ) : r.isOpen ? (
                            <Label color="green" isCompact>
                              Open
                            </Label>
                          ) : null}
                          {r.sandboxStatus ? (
                            <Label
                              color={
                                r.sandboxStatus === 'running'
                                  ? 'green'
                                  : r.sandboxStatus === 'creating' ||
                                      r.sandboxStatus === 'pending'
                                    ? 'purple'
                                    : r.sandboxStatus === 'error'
                                      ? 'red'
                                      : 'grey'
                              }
                              isCompact
                            >
                              {r.sandboxStatus}
                            </Label>
                          ) : null}
                        </span>
                        <span className="open-project-row-sub">
                          <span className="open-project-row-slug">{r.slug}</span>
                          {r.description ? (
                            <span className="open-project-row-desc">· {r.description}</span>
                          ) : null}
                        </span>
                      </span>
                      <span className="open-project-row-meta">
                        <span className="open-project-chip" title="Template">
                          {r.templateIcon} {r.templateLabel}
                        </span>
                        <span className="open-project-stats">
                          {r.repoCount} repo{r.repoCount === 1 ? '' : 's'}
                          {r.harnessCount > 0
                            ? ` · ${r.harnessCount} harness${r.harnessCount === 1 ? '' : 'es'}`
                            : ''}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={openSelected} isDisabled={!selected}>
          {selected?.isOpen && !selected.isActive
            ? 'Switch to project'
            : selected?.isActive
              ? 'Focus project'
              : selected?.fromApi &&
                  selected.sandboxStatus &&
                  selected.sandboxStatus !== 'running'
                ? 'Open & start sandbox'
                : 'Open project'}
        </Button>
        <Button variant="secondary" icon={<PlusCircleIcon />} onClick={goCreate}>
          Create project
        </Button>
        <Button variant="link" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
