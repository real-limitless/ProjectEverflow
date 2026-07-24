import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  PageSection,
  SearchInput,
  Spinner,
  Tab,
  Tabs,
  TabTitleText,
} from '@patternfly/react-core'
import CatalogIcon from '@patternfly/react-icons/dist/esm/icons/catalog-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import { Link, useSearchParams } from 'react-router-dom'
import {
  LOCAL_MARKETPLACE_CATALOG,
  MARKETPLACE_TABS,
  itemsForTab,
  type MarketplaceCatalog,
  type MarketplaceItem,
  type MarketplaceKind,
  type MarketplaceTab,
} from '@/data/marketplace'
import {
  getMarketplaceCatalog,
  getMarketplaceInstalled,
  installMarketplaceItem,
  isDemoMode,
  listProjects,
  type ApiProject,
} from '@/lib/api'
import { pushToast } from '@/lib/studioToast'
import { useAuthStore } from '@/store/authStore'
import { usePlaygroundStore } from '@/store/playgroundStore'

function parseTab(raw: string | null): MarketplaceTab {
  const hit = MARKETPLACE_TABS.find((t) => t.id === raw)
  return hit?.id ?? 'skills'
}

function originLabel(origin: string): string {
  if (origin === 'ecc') return 'ECC'
  if (origin === 'curated') return 'Curated'
  return origin
}

export function MarketplacePage() {
  const [params, setParams] = useSearchParams()
  const tab = parseTab(params.get('tab'))
  const org = useAuthStore((s) => s.org)
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)

  const [catalog, setCatalog] = useState<MarketplaceCatalog>(LOCAL_MARKETPLACE_CATALOG)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [installItem, setInstallItem] = useState<MarketplaceItem | null>(null)
  const [projects, setProjects] = useState<ApiProject[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [installedByProject, setInstalledByProject] = useState<
    Record<string, Set<string>>
  >({})

  const setTab = (next: MarketplaceTab) => {
    const nextParams = new URLSearchParams(params)
    nextParams.set('tab', next)
    setParams(nextParams, { replace: true })
  }

  useEffect(() => {
    if (demoMode) {
      setCatalog(LOCAL_MARKETPLACE_CATALOG)
      return
    }
    setCatalogLoading(true)
    void getMarketplaceCatalog()
      .then(setCatalog)
      .catch(() => {
        setCatalog(LOCAL_MARKETPLACE_CATALOG)
      })
      .finally(() => setCatalogLoading(false))
  }, [demoMode])

  const items = useMemo(() => {
    const rows = itemsForTab(catalog, tab)
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.id.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        (item.tags || []).some((t) => t.toLowerCase().includes(q)),
    )
  }, [catalog, tab, query])

  const counts = useMemo(
    () => ({
      skills: catalog.skills.length,
      commands: catalog.commands.length,
      plugins: catalog.plugins.length,
      tools: catalog.tools.length,
      mcp: catalog.mcps.length,
    }),
    [catalog],
  )

  const installedKey = (kind: MarketplaceKind, id: string) => `${kind}:${id}`

  const refreshInstalledFor = useCallback(async (projectIds: string[]) => {
    if (demoMode) return
    const updates: Record<string, Set<string>> = {}
    await Promise.all(
      projectIds.map(async (pid) => {
        try {
          const res = await getMarketplaceInstalled(pid)
          updates[pid] = new Set(
            (res.items || []).map((i) => installedKey(i.kind as MarketplaceKind, i.id)),
          )
        } catch {
          /* sandbox stopped — leave prior state */
        }
      }),
    )
    setInstalledByProject((prev) => ({ ...prev, ...updates }))
  }, [demoMode])

  const openInstall = async (item: MarketplaceItem) => {
    setInstallItem(item)
    setSelectedIds(new Set(currentProjectId ? [currentProjectId] : []))
    if (demoMode || !org?.id) {
      setProjects([])
      return
    }
    setProjectsLoading(true)
    try {
      const rows = await listProjects(org.id)
      setProjects(rows)
      const running = rows.filter((p) => p.sandbox_status === 'running').map((p) => p.id)
      if (running.length) void refreshInstalledFor(running)
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load projects', { kind: 'danger' })
    } finally {
      setProjectsLoading(false)
    }
  }

  const toggleProject = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const handleInstall = async () => {
    if (!installItem) return
    if (demoMode) {
      pushToast('Sign in and open an API project with a running sandbox to install.', {
        kind: 'warning',
      })
      return
    }
    const targets = projects.filter((p) => selectedIds.has(p.id))
    if (!targets.length) {
      pushToast('Select at least one project', { kind: 'warning' })
      return
    }
    const blocked = targets.filter((p) => p.sandbox_status !== 'running' && installItem.kind !== 'tool')
    if (blocked.length) {
      pushToast(
        `Sandbox must be running for: ${blocked.map((p) => p.name).join(', ')}`,
        { kind: 'danger' },
      )
      return
    }
    setInstalling(true)
    let ok = 0
    let fail = 0
    for (const project of targets) {
      try {
        await installMarketplaceItem(project.id, installItem.kind, installItem.id)
        ok += 1
        window.dispatchEvent(
          new CustomEvent('everflow:harness-updated', { detail: { projectId: project.id } }),
        )
      } catch (e) {
        fail += 1
        pushToast(
          `${project.name}: ${e instanceof Error ? e.message : 'Install failed'}`,
          { kind: 'danger' },
        )
      }
    }
    setInstalling(false)
    if (ok) {
      pushToast(
        `Installed “${installItem.name}” on ${ok} project${ok === 1 ? '' : 's'}`,
        { kind: 'success' },
      )
      void refreshInstalledFor(targets.map((p) => p.id))
    }
    if (!fail) setInstallItem(null)
  }

  const isInstalledAnywhere = (item: MarketplaceItem) => {
    const key = installedKey(item.kind, item.id)
    return Object.values(installedByProject).some((set) => set.has(key))
  }

  return (
    <>
      <PageSection aria-labelledby="marketplace-title">
        <Content>
          <h1 id="marketplace-title">Marketplace</h1>
          <p>
            Browse skills, commands, plugins, HTTP tools, and MCP servers — then add them to one or
            more projects. Skills and commands are sourced from{' '}
            <a href="https://github.com/affaan-m/ECC" target="_blank" rel="noreferrer">
              ECC
            </a>
            ; plugins include Graphify, Oh My OpenCode, and Headroom.
          </p>
        </Content>
      </PageSection>
      <PageSection className="marketplace-toolbar-section">
        <Tabs
          activeKey={tab}
          onSelect={(_e, key) => setTab(key as MarketplaceTab)}
          aria-label="Marketplace categories"
        >
          {MARKETPLACE_TABS.map((t) => (
            <Tab
              key={t.id}
              eventKey={t.id}
              title={
                <TabTitleText>
                  {t.label} ({counts[t.id]})
                </TabTitleText>
              }
            />
          ))}
        </Tabs>
        <div className="marketplace-toolbar">
          <SearchInput
            className="marketplace-search"
            placeholder={`Search ${tab}…`}
            value={query}
            onChange={(_e, v) => setQuery(v)}
            onClear={() => setQuery('')}
            aria-label="Search marketplace"
          />
          {catalogLoading ? <Spinner size="md" aria-label="Loading catalog" /> : null}
        </div>
      </PageSection>
      <PageSection isFilled className="marketplace-grid-section" aria-label="Marketplace items">
        {items.length === 0 ? (
          <EmptyState
            variant={EmptyStateVariant.sm}
            titleText="No matches"
            headingLevel="h2"
            icon={CatalogIcon}
          >
            <EmptyStateBody>Try another search or category.</EmptyStateBody>
          </EmptyState>
        ) : (
          <div className="marketplace-grid">
            {items.map((item) => (
              <article key={`${item.kind}-${item.id}`} className="marketplace-card">
                <div className="marketplace-card-head">
                  <h2 className="marketplace-card-title">{item.name}</h2>
                  <Label color={item.origin === 'ecc' ? 'blue' : 'green'} isCompact>
                    {originLabel(item.origin)}
                  </Label>
                </div>
                <p className="marketplace-card-desc">{item.description}</p>
                <div className="marketplace-card-foot">
                  {item.source?.startsWith('http') ? (
                    <a
                      className="marketplace-card-source"
                      href={item.source}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Source <ExternalLinkAltIcon />
                    </a>
                  ) : (
                    <span className="marketplace-card-source">{item.source}</span>
                  )}
                  <div className="marketplace-card-actions">
                    {isInstalledAnywhere(item) ? (
                      <Label color="grey" isCompact>
                        Installed
                      </Label>
                    ) : null}
                    <Button variant="primary" size="sm" onClick={() => void openInstall(item)}>
                      Add to project
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </PageSection>

      <Modal
        isOpen={Boolean(installItem)}
        onClose={() => {
          if (!installing) setInstallItem(null)
        }}
        variant={ModalVariant.medium}
        aria-labelledby="marketplace-install-title"
      >
        <ModalHeader
          title={installItem ? `Add “${installItem.name}”` : 'Add to projects'}
          labelId="marketplace-install-title"
          description={
            installItem?.kind === 'tool'
              ? 'Creates an HTTP tool on each selected project (sandbox not required).'
              : 'Requires a running sandbox. Writes into the project OpenCode harness.'
          }
        />
        <ModalBody>
          {demoMode || !org?.id ? (
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="Sign in to install"
              headingLevel="h3"
            >
              <EmptyStateBody>
                Marketplace install needs an authenticated org and project.{' '}
                <Button variant="link" isInline onClick={() => setOpenProjectModal(true)}>
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
                const toolOk = installItem?.kind === 'tool'
                const disabled = !toolOk && !running
                const key = installItem
                  ? installedKey(installItem.kind, installItem.id)
                  : ''
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
                      onChange={(_e, checked) => toggleProject(p.id, checked)}
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
            onClick={() => void handleInstall()}
            isDisabled={installing || !selectedIds.size || demoMode || !org?.id}
            isLoading={installing}
          >
            Install
          </Button>
          <Button variant="link" onClick={() => setInstallItem(null)} isDisabled={installing}>
            Cancel
          </Button>
          <Link className="pf-v6-c-button pf-m-secondary" to="/" aria-disabled={installing}>
            Open Playground
          </Link>
        </ModalFooter>
      </Modal>
    </>
  )
}
