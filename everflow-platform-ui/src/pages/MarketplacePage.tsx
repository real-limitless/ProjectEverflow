import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  Label,
  PageSection,
  Pagination,
  SearchInput,
  Spinner,
  Tab,
  Tabs,
  TabTitleText,
} from '@patternfly/react-core'
import CatalogIcon from '@patternfly/react-icons/dist/esm/icons/catalog-icon'
import { useSearchParams } from 'react-router-dom'
import { MarketplaceCard } from '@/components/marketplace/MarketplaceCard'
import { MarketplaceInstallModal } from '@/components/marketplace/MarketplaceInstallModal'
import {
  LOCAL_MARKETPLACE_CATALOG,
  MARKETPLACE_TABS,
  collectOrigins,
  collectTags,
  featuredItems,
  filterMarketplaceItems,
  itemsForTab,
  originLabel,
  paginateItems,
  type MarketplaceCatalog,
  type MarketplaceTab,
} from '@/data/marketplace'
import { getMarketplaceCatalog, isDemoMode } from '@/lib/api'
import { useMarketplaceInstall } from '@/hooks/useMarketplaceInstall'
import { useAuthStore } from '@/store/authStore'

function parseTab(raw: string | null): MarketplaceTab {
  const hit = MARKETPLACE_TABS.find((t) => t.id === raw)
  return hit?.id ?? 'skills'
}

function parsePositiveInt(raw: string | null, fallback: number): number {
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 1) return fallback
  return Math.floor(n)
}

export function MarketplacePage() {
  const [params, setParams] = useSearchParams()
  const tab = parseTab(params.get('tab'))
  const query = params.get('q') || ''
  const tag = params.get('tag') || ''
  const origin = params.get('origin') || ''
  const page = parsePositiveInt(params.get('page'), 1)
  const pageSize = [12, 24, 48].includes(parsePositiveInt(params.get('pageSize'), 12))
    ? parsePositiveInt(params.get('pageSize'), 12)
    : 12

  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  const install = useMarketplaceInstall()

  const [catalog, setCatalog] = useState<MarketplaceCatalog>(LOCAL_MARKETPLACE_CATALOG)
  const [catalogLoading, setCatalogLoading] = useState(false)

  const patchParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const setTab = (next: MarketplaceTab) => {
    patchParams({ tab: next, page: '1', tag: null, origin: null })
  }

  useEffect(() => {
    if (demoMode) {
      setCatalog(LOCAL_MARKETPLACE_CATALOG)
      return
    }
    setCatalogLoading(true)
    void getMarketplaceCatalog()
      .then(setCatalog)
      .catch(() => setCatalog(LOCAL_MARKETPLACE_CATALOG))
      .finally(() => setCatalogLoading(false))
  }, [demoMode])

  const tabItems = useMemo(() => itemsForTab(catalog, tab), [catalog, tab])

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

  const filtered = useMemo(
    () => filterMarketplaceItems(tabItems, { query, tag, origin }),
    [tabItems, query, tag, origin],
  )

  const { pageItems, total, page: safePage, pageCount } = useMemo(
    () => paginateItems(filtered, page, pageSize),
    [filtered, page, pageSize],
  )

  // Keep URL page in range after filter changes
  useEffect(() => {
    if (page !== safePage) {
      patchParams({ page: String(safePage) })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when pagination clamps
  }, [safePage, page])

  const featured = useMemo(() => featuredItems(catalog, tab, 8), [catalog, tab])
  const tags = useMemo(() => collectTags(tabItems, 10), [tabItems])
  const origins = useMemo(() => collectOrigins(tabItems), [tabItems])

  return (
    <>
      <PageSection className="mp-hero" aria-labelledby="marketplace-title">
        <div className="mp-hero-inner">
          <Content>
            <h1 id="marketplace-title">Marketplace</h1>
            <p className="mp-hero-lead">
              Discover skills, commands, plugins, tools, and MCP servers — install them on a project
              harness or open a skill to try it live.
            </p>
          </Content>
          <div className="mp-hero-search">
            <SearchInput
              className="mp-search"
              placeholder={`Search ${tab}…`}
              value={query}
              onChange={(_e, v) => patchParams({ q: v || null, page: '1' })}
              onClear={() => patchParams({ q: null, page: '1' })}
              aria-label="Search marketplace"
            />
            {catalogLoading ? <Spinner size="md" aria-label="Loading catalog" /> : null}
          </div>
        </div>
      </PageSection>

      <PageSection className="mp-toolbar-section" type="tabs">
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
      </PageSection>

      {featured.length > 0 && !query && !tag && !origin ? (
        <PageSection className="mp-featured-section" aria-label="Featured">
          <div className="mp-section-head">
            <h2 className="mp-section-title">Featured</h2>
          </div>
          <div className="mp-featured-rail">
            {featured.map((item) => (
              <MarketplaceCard
                key={`feat-${item.kind}-${item.id}`}
                item={item}
                featured
                installed={install.isInstalledAnywhere(item)}
                onGet={(i) => void install.openInstall(i)}
              />
            ))}
          </div>
        </PageSection>
      ) : null}

      <PageSection className="mp-filters-section">
        <div className="mp-filters">
          {origins.length > 1 ? (
            <div className="mp-chip-row" role="group" aria-label="Filter by origin">
              <Button
                variant={origin ? 'secondary' : 'primary'}
                size="sm"
                className="mp-chip"
                onClick={() => patchParams({ origin: null, page: '1' })}
              >
                All sources
              </Button>
              {origins.map((o) => (
                <Button
                  key={o}
                  variant={origin === o ? 'primary' : 'secondary'}
                  size="sm"
                  className="mp-chip"
                  onClick={() =>
                    patchParams({ origin: origin === o ? null : o, page: '1' })
                  }
                >
                  {originLabel(o)}
                </Button>
              ))}
            </div>
          ) : null}
          {tags.length ? (
            <div className="mp-chip-row" role="group" aria-label="Filter by tag">
              {tags.map((t) => (
                <Label
                  key={t}
                  color={tag === t ? 'blue' : 'grey'}
                  onClick={() => patchParams({ tag: tag === t ? null : t, page: '1' })}
                  className="mp-tag-chip"
                  isCompact
                >
                  {t}
                </Label>
              ))}
            </div>
          ) : null}
          <div className="mp-result-meta">
            <span>
              {total} result{total === 1 ? '' : 's'}
              {query ? ` for “${query}”` : ''}
            </span>
          </div>
        </div>
      </PageSection>

      <PageSection isFilled className="mp-grid-section" aria-label="Marketplace items">
        {pageItems.length === 0 ? (
          <EmptyState
            variant={EmptyStateVariant.sm}
            titleText="No matches"
            headingLevel="h2"
            icon={CatalogIcon}
          >
            <EmptyStateBody>Try another search, tag, or category.</EmptyStateBody>
          </EmptyState>
        ) : (
          <div className="mp-grid">
            {pageItems.map((item) => (
              <MarketplaceCard
                key={`${item.kind}-${item.id}`}
                item={item}
                installed={install.isInstalledAnywhere(item)}
                onGet={(i) => void install.openInstall(i)}
              />
            ))}
          </div>
        )}

        {total > 0 ? (
          <div className="mp-pagination">
            <Pagination
              itemCount={total}
              perPage={pageSize}
              page={safePage}
              onSetPage={(_e, p) => patchParams({ page: String(p) })}
              onPerPageSelect={(_e, per) =>
                patchParams({ pageSize: String(per), page: '1' })
              }
              perPageOptions={[
                { title: '12', value: 12 },
                { title: '24', value: 24 },
                { title: '48', value: 48 },
              ]}
              variant="bottom"
              titles={{
                paginationAriaLabel: 'Marketplace pagination',
              }}
            />
            <span className="mp-page-indicator">
              Page {safePage} of {pageCount}
            </span>
          </div>
        ) : null}
      </PageSection>

      <MarketplaceInstallModal
        item={install.installItem}
        open={Boolean(install.installItem)}
        onClose={install.closeInstall}
        demoMode={install.demoMode}
        hasOrg={Boolean(install.org?.id)}
        projects={install.projects}
        projectsLoading={install.projectsLoading}
        selectedIds={install.selectedIds}
        onToggleProject={install.toggleProject}
        installing={install.installing}
        onInstall={() => void install.handleInstall()}
        installedByProject={install.installedByProject}
        installedKey={install.installedKey}
        onOpenProjectModal={() => install.setOpenProjectModal(true)}
      />
    </>
  )
}
