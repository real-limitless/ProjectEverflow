import { useEffect, useMemo, useState } from 'react'
import {
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  PageSection,
  SearchInput,
  Tab,
  Tabs,
  TabTitleText,
} from '@patternfly/react-core'
import CubeIcon from '@patternfly/react-icons/dist/esm/icons/cube-icon'
import { useSearchParams } from 'react-router-dom'
import { HarnessCard } from '@/components/harness/HarnessCard'
import {
  HARNESS_CATALOG,
  HARNESS_CATEGORY_LABELS,
  HARNESS_CATEGORY_ORDER,
  enabledHarnessIds,
  harnessesFromApi,
  type HarnessCategory,
  type HarnessDef,
} from '@/data/harnesses'
import { getProject, listVisibleProjectIds } from '@/data/projects'
import { isDemoMode, listProjects, type ApiProject } from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { usePlaygroundStore } from '@/store/playgroundStore'

type CategoryTab = 'all' | HarnessCategory

function parseCategory(raw: string | null): CategoryTab {
  if (!raw || raw === 'all') return 'all'
  if ((HARNESS_CATEGORY_ORDER as string[]).includes(raw)) return raw as HarnessCategory
  return 'all'
}

function matchesQuery(h: HarnessDef, q: string): boolean {
  if (!q) return true
  const hay = `${h.name} ${h.description} ${h.id} ${h.category}`.toLowerCase()
  return hay.includes(q.toLowerCase())
}

export function HarnessesPage() {
  const [params, setParams] = useSearchParams()
  const category = parseCategory(params.get('cat'))
  const query = params.get('q') || ''

  const org = useAuthStore((s) => s.org)
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  // Re-read catalog when projects are created/synced
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)

  const [apiProjects, setApiProjects] = useState<ApiProject[]>([])

  const patchParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  useEffect(() => {
    if (!org?.id || demoMode) {
      setApiProjects([])
      return
    }
    let cancelled = false
    void listProjects(org.id)
      .then((list) => {
        if (!cancelled) setApiProjects(list)
      })
      .catch(() => {
        if (!cancelled) setApiProjects([])
      })
    return () => {
      cancelled = true
    }
  }, [org?.id, demoMode])

  const usageByHarness = useMemo(() => {
    const counts = new Map<string, number>()
    if (!demoMode && apiProjects.length > 0) {
      for (const p of apiProjects) {
        for (const id of harnessesFromApi(p.harnesses).map((h) => h.id)) {
          counts.set(id, (counts.get(id) || 0) + 1)
        }
      }
      return counts
    }
    for (const pid of listVisibleProjectIds()) {
      const p = getProject(pid)
      if (!p) continue
      for (const id of enabledHarnessIds(p.harnesses)) {
        counts.set(id, (counts.get(id) || 0) + 1)
      }
    }
    return counts
  }, [apiProjects, demoMode, catalogVersion])

  const counts = useMemo(() => {
    const byCat: Record<string, number> = { all: HARNESS_CATALOG.length }
    for (const cat of HARNESS_CATEGORY_ORDER) byCat[cat] = 0
    for (const h of HARNESS_CATALOG) {
      byCat[h.category] = (byCat[h.category] || 0) + 1
    }
    return byCat
  }, [])

  const filtered = useMemo(() => {
    return HARNESS_CATALOG.filter((h) => {
      if (category !== 'all' && h.category !== category) return false
      return matchesQuery(h, query)
    })
  }, [category, query])

  return (
    <>
      <PageSection className="hn-hero" aria-labelledby="harnesses-title">
        <div className="hn-hero-inner">
          <Content>
            <h1 id="harnesses-title">Harnesses</h1>
            <p className="hn-hero-lead">
              Harnesses install into each project&apos;s microVM — agent CLIs, CI helpers, Postgres
              tools, and related sandboxes. Choose them when you create a project, or change them
              anytime in <strong>Project settings → Harnesses</strong> (saving reconfigures the
              sandbox).
            </p>
          </Content>
          <div className="hn-hero-search">
            <SearchInput
              className="hn-search"
              placeholder="Search harnesses…"
              value={query}
              onChange={(_e, v) => patchParams({ q: v || null })}
              onClear={() => patchParams({ q: null })}
              aria-label="Search harnesses"
            />
          </div>
        </div>
      </PageSection>

      <PageSection className="hn-toolbar-section" type="tabs">
        <Tabs
          activeKey={category}
          onSelect={(_e, key) =>
            patchParams({ cat: key === 'all' ? null : String(key) })
          }
          aria-label="Harness categories"
        >
          {(
            [
              { id: 'all' as const, label: `All (${counts.all})` },
              ...HARNESS_CATEGORY_ORDER.filter((c) => (counts[c] || 0) > 0).map(
                (c) => ({
                  id: c as CategoryTab,
                  label: `${HARNESS_CATEGORY_LABELS[c]} (${counts[c]})`,
                }),
              ),
            ] as { id: CategoryTab; label: string }[]
          ).map((t) => (
            <Tab
              key={t.id}
              eventKey={t.id}
              title={<TabTitleText>{t.label}</TabTitleText>}
            />
          ))}
        </Tabs>
      </PageSection>

      <PageSection className="hn-filters-section">
        <div className="hn-result-meta">
          {filtered.length} harness{filtered.length === 1 ? '' : 'es'}
          {query ? ` matching “${query}”` : ''}
        </div>
      </PageSection>

      <PageSection isFilled className="hn-grid-section" aria-label="Harness catalog">
        {filtered.length === 0 ? (
          <EmptyState
            variant={EmptyStateVariant.sm}
            titleText="No matches"
            headingLevel="h2"
            icon={CubeIcon}
          >
            <EmptyStateBody>Try another search or category.</EmptyStateBody>
          </EmptyState>
        ) : (
          <div className="hn-grid">
            {filtered.map((h) => (
              <HarnessCard
                key={h.id}
                harness={h}
                usedByCount={usageByHarness.get(h.id)}
              />
            ))}
          </div>
        )}
      </PageSection>
    </>
  )
}
