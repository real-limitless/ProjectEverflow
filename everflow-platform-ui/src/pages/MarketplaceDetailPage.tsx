import { useEffect, useState } from 'react'
import {
  Button,
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  Label,
  PageSection,
  Spinner,
} from '@patternfly/react-core'
import AngleLeftIcon from '@patternfly/react-icons/dist/esm/icons/angle-left-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import { Link, useParams } from 'react-router-dom'
import { MarketplaceInstallModal } from '@/components/marketplace/MarketplaceInstallModal'
import { MarketplaceItemIcon } from '@/components/marketplace/MarketplaceItemIcon'
import { SkillTryDrawer } from '@/components/marketplace/SkillTryDrawer'
import {
  LOCAL_MARKETPLACE_CATALOG,
  findCatalogItem,
  kindLabel,
  kindToTab,
  originLabel,
  parseKindParam,
  supportsContentPreview,
  supportsTryChat,
  type MarketplaceCatalog,
  type MarketplaceItem,
} from '@/data/marketplace'
import {
  getMarketplaceCatalog,
  getMarketplaceItem,
  getMarketplaceItemContent,
  isDemoMode,
} from '@/lib/api'
import { markdownToHtml } from '@/lib/chatMarkdown'
import { useMarketplaceInstall } from '@/hooks/useMarketplaceInstall'
import { useAuthStore } from '@/store/authStore'

export function MarketplaceDetailPage() {
  const { kind: kindParam, itemId: rawId } = useParams()
  const kind = parseKindParam(kindParam)
  const itemId = rawId ? decodeURIComponent(rawId) : ''
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  const install = useMarketplaceInstall()

  const [catalog, setCatalog] = useState<MarketplaceCatalog>(LOCAL_MARKETPLACE_CATALOG)
  const [item, setItem] = useState<MarketplaceItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [content, setContent] = useState<string | null>(null)
  const [contentLoading, setContentLoading] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const [tryOpen, setTryOpen] = useState(false)

  useEffect(() => {
    if (demoMode) {
      setCatalog(LOCAL_MARKETPLACE_CATALOG)
      return
    }
    void getMarketplaceCatalog()
      .then(setCatalog)
      .catch(() => setCatalog(LOCAL_MARKETPLACE_CATALOG))
  }, [demoMode])

  useEffect(() => {
    if (!kind || !itemId) {
      setItem(null)
      setLoading(false)
      return
    }
    setLoading(true)
    const local = findCatalogItem(catalog, kind, itemId) || null
    setItem(local)

    if (demoMode) {
      setLoading(false)
      return
    }

    let cancelled = false
    void getMarketplaceItem(kind, itemId)
      .then((row) => {
        if (!cancelled) setItem(row as MarketplaceItem)
      })
      .catch(() => {
        /* keep local catalog hit */
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [kind, itemId, catalog, demoMode])

  useEffect(() => {
    if (!item || !supportsContentPreview(item.kind)) {
      setContent(null)
      setContentError(null)
      setContentLoading(false)
      return
    }
    setContentLoading(true)
    setContentError(null)
    let cancelled = false
    void getMarketplaceItemContent(item.kind, item.id)
      .then((res) => {
        if (!cancelled) setContent(res.content)
      })
      .catch((e) => {
        if (!cancelled) {
          setContent(null)
          // Soft-fail offline/demo; hard message only when signed in to API
          setContentError(
            demoMode
              ? null
              : e instanceof Error
                ? e.message
                : 'Could not load skill content',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [item, demoMode])

  if (!kind || !itemId) {
    return (
      <PageSection>
        <EmptyState titleText="Invalid marketplace link" headingLevel="h2">
          <EmptyStateBody>
            <Link to="/marketplace">Back to Marketplace</Link>
          </EmptyStateBody>
        </EmptyState>
      </PageSection>
    )
  }

  if (loading && !item) {
    return (
      <PageSection>
        <Spinner aria-label="Loading item" />
      </PageSection>
    )
  }

  if (!item) {
    return (
      <PageSection>
        <EmptyState
          variant={EmptyStateVariant.sm}
          titleText="Item not found"
          headingLevel="h2"
        >
          <EmptyStateBody>
            No marketplace entry for {kind}/{itemId}.{' '}
            <Link to={`/marketplace?tab=${kindToTab(kind)}`}>Browse {kindLabel(kind)}s</Link>
          </EmptyStateBody>
        </EmptyState>
      </PageSection>
    )
  }

  const backTab = kindToTab(item.kind)

  return (
    <>
      <PageSection className="mp-detail-nav">
        <Link className="mp-back-link" to={`/marketplace?tab=${backTab}`}>
          <AngleLeftIcon /> Back to {kindLabel(item.kind)}s
        </Link>
      </PageSection>

      <PageSection className="mp-detail-hero">
        <div className="mp-detail-hero-inner">
          <MarketplaceItemIcon id={item.id} name={item.name} size="lg" />
          <div className="mp-detail-hero-text">
            <div className="mp-detail-labels">
              <Label isCompact color="grey">
                {kindLabel(item.kind)}
              </Label>
              <Label
                isCompact
                color={
                  item.origin === 'everflow' ? 'green' : item.origin === 'ecc' ? 'blue' : 'grey'
                }
              >
                {originLabel(item.origin)}
              </Label>
              {install.isInstalledAnywhere(item) ? (
                <Label isCompact color="blue">
                  Installed
                </Label>
              ) : null}
            </div>
            <Content>
              <h1 className="mp-detail-title">{item.name}</h1>
              <p className="mp-detail-desc">{item.description}</p>
            </Content>
            <div className="mp-detail-actions">
              <Button variant="primary" onClick={() => void install.openInstall(item)}>
                Get
              </Button>
              {supportsTryChat(item.kind) ? (
                <Button variant="secondary" onClick={() => setTryOpen(true)}>
                  Try skill
                </Button>
              ) : null}
              {item.source?.startsWith('http') ? (
                <a
                  className="pf-v6-c-button pf-m-link"
                  href={item.source}
                  target="_blank"
                  rel="noreferrer"
                >
                  Source <ExternalLinkAltIcon />
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </PageSection>

      <PageSection className="mp-detail-body">
        <div className="mp-detail-grid">
          <section className="mp-detail-main" aria-labelledby="mp-about">
            <h2 id="mp-about">About</h2>
            <p>{item.description}</p>
            {(item.tags || []).length ? (
              <div className="mp-detail-tags">
                {item.tags!.map((t) => (
                  <Label key={t} isCompact color="grey">
                    {t}
                  </Label>
                ))}
              </div>
            ) : null}

            {item.kind === 'plugin' && item.install ? (
              <div className="mp-detail-block">
                <h3>What’s included</h3>
                <ul>
                  {item.install.plugin?.map((p) => (
                    <li key={p}>Plugin: {p}</li>
                  ))}
                  {item.install.skills?.map((s) => (
                    <li key={s.id}>Skill: {s.id}</li>
                  ))}
                  {item.install.mcp
                    ? Object.keys(item.install.mcp).map((k) => <li key={k}>MCP: {k}</li>)
                    : null}
                </ul>
              </div>
            ) : null}

            {item.kind === 'mcp' && item.mcpConfig ? (
              <div className="mp-detail-block">
                <h3>MCP config keys</h3>
                <ul>
                  {Object.keys(item.mcpConfig).map((k) => (
                    <li key={k}>
                      <code>{k}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {item.kind === 'tool' && item.httpTool ? (
              <div className="mp-detail-block">
                <h3>HTTP tool</h3>
                <p>
                  <code>
                    {item.httpTool.method} {item.httpTool.url_template}
                  </code>
                </p>
              </div>
            ) : null}

            {supportsContentPreview(item.kind) ? (
              <div className="mp-detail-block" aria-labelledby="mp-skill-body">
                <h2 id="mp-skill-body">Skill definition</h2>
                {contentLoading ? (
                  <Spinner size="lg" aria-label="Loading skill content" />
                ) : content ? (
                  <div
                    className="mp-skill-md"
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(content) }}
                  />
                ) : (
                  <p className="mp-muted">
                    {contentError ||
                      'Skill body is resolved when you install or when the content API is available.'}
                  </p>
                )}
              </div>
            ) : null}
          </section>

          <aside className="mp-detail-aside">
            <div className="mp-aside-card">
              <h3>Information</h3>
              <dl className="mp-info-dl">
                <dt>ID</dt>
                <dd>
                  <code>{item.id}</code>
                </dd>
                <dt>Kind</dt>
                <dd>{kindLabel(item.kind)}</dd>
                <dt>Origin</dt>
                <dd>{originLabel(item.origin)}</dd>
                {item.source ? (
                  <>
                    <dt>Source</dt>
                    <dd className="mp-info-source">
                      {item.source.startsWith('http') ? (
                        <a href={item.source} target="_blank" rel="noreferrer">
                          {item.source}
                        </a>
                      ) : (
                        item.source
                      )}
                    </dd>
                  </>
                ) : null}
              </dl>
              {supportsTryChat(item.kind) ? (
                <Button isBlock variant="secondary" onClick={() => setTryOpen(true)}>
                  Open try chat
                </Button>
              ) : null}
              <Button isBlock variant="primary" onClick={() => void install.openInstall(item)}>
                Get for project
              </Button>
            </div>
          </aside>
        </div>
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

      <SkillTryDrawer item={item} open={tryOpen} onClose={() => setTryOpen(false)} />
    </>
  )
}
