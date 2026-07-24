import { useEffect, useMemo, useState } from 'react'
import {
  Content,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  FormSelect,
  FormSelectOption,
  PageSection,
  Spinner,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import ChartLineIcon from '@patternfly/react-icons/dist/esm/icons/chart-line-icon'
import {
  Chart,
  ChartAxis,
  ChartBar,
  ChartGroup,
  ChartLine,
  ChartThemeColor,
  ChartVoronoiContainer,
} from '@patternfly/react-charts/victory'
import {
  getUsageSummary,
  isDemoMode,
  listProjects,
  type AiUsageSummary,
  type ApiProject,
} from '@/lib/api'
import { useAuthStore } from '@/store/authStore'

type RangeKey = '7d' | '30d' | '90d'
type ScopeKey = 'me' | 'org'

function rangeBounds(range: RangeKey): { from: string; to: string } {
  const to = new Date()
  const from = new Date(to)
  const days = range === '7d' ? 7 : range === '90d' ? 90 : 30
  from.setUTCDate(from.getUTCDate() - (days - 1))
  from.setUTCHours(0, 0, 0, 0)
  return { from: from.toISOString(), to: to.toISOString() }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function shortDate(isoDate: string): string {
  // series dates are YYYY-MM-DD (or similar)
  const d = isoDate.slice(5) // MM-DD
  return d || isoDate
}

function modelLabel(provider: string | null, model: string | null): string {
  if (provider && model) return `${provider}/${model}`
  return model || provider || 'Unknown'
}

export function UsagePage() {
  const org = useAuthStore((s) => s.org)
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()

  const [range, setRange] = useState<RangeKey>('30d')
  const [scope, setScope] = useState<ScopeKey>('me')
  const [projectId, setProjectId] = useState<string>('')
  const [projects, setProjects] = useState<ApiProject[]>([])
  const [summary, setSummary] = useState<AiUsageSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!org?.id || demoMode) {
      setProjects([])
      return
    }
    let cancelled = false
    void listProjects(org.id)
      .then((list) => {
        if (!cancelled) setProjects(list)
      })
      .catch(() => {
        if (!cancelled) setProjects([])
      })
    return () => {
      cancelled = true
    }
  }, [org?.id, demoMode])

  useEffect(() => {
    if (!org?.id || demoMode) {
      setSummary(null)
      setError(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const { from, to } = rangeBounds(range)
    void getUsageSummary(org.id, {
      scope,
      from,
      to,
      project_id: projectId || undefined,
    })
      .then((data) => {
        if (!cancelled) setSummary(data)
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setSummary(null)
          setError(e.message || 'Failed to load usage')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [org?.id, demoMode, range, scope, projectId])

  const seriesTokens = useMemo(
    () =>
      (summary?.series_daily || []).map((p, i) => ({
        name: 'Tokens',
        x: shortDate(p.date),
        y: p.tokens,
        i,
      })),
    [summary],
  )
  const seriesMessages = useMemo(
    () =>
      (summary?.series_daily || []).map((p) => ({
        name: 'Turns',
        x: shortDate(p.date),
        y: p.messages,
      })),
    [summary],
  )
  const byModel = useMemo(
    () =>
      (summary?.by_model || []).slice(0, 8).map((row) => ({
        name: modelLabel(row.provider, row.model),
        x: modelLabel(row.provider, row.model),
        y: row.tokens,
      })),
    [summary],
  )
  const byProject = useMemo(
    () =>
      (summary?.by_project || []).slice(0, 8).map((row) => ({
        name: row.project_name,
        x: row.project_name,
        y: row.tokens,
      })),
    [summary],
  )
  const byUser = useMemo(
    () =>
      (summary?.by_user || []).slice(0, 8).map((row) => ({
        name: row.email,
        x: row.email.split('@')[0] || row.email,
        y: row.tokens,
      })),
    [summary],
  )

  const empty =
    !loading &&
    !error &&
    summary != null &&
    summary.totals.messages === 0

  return (
    <>
      <PageSection aria-labelledby="usage-title">
        <Content>
          <h1 id="usage-title">Usage</h1>
          <p>
            AI chat token usage across {scope === 'me' ? 'your' : 'organization'}{' '}
            projects.
            {org?.name ? ` · ${org.name}` : ''}
          </p>
        </Content>
      </PageSection>

      <PageSection className="usage-toolbar-section">
        <div className="usage-toolbar">
          <ToggleGroup aria-label="Usage scope">
            <ToggleGroupItem
              text="My usage"
              isSelected={scope === 'me'}
              onChange={() => setScope('me')}
            />
            <ToggleGroupItem
              text="Organization"
              isSelected={scope === 'org'}
              onChange={() => setScope('org')}
            />
          </ToggleGroup>
          <ToggleGroup aria-label="Date range">
            {(['7d', '30d', '90d'] as RangeKey[]).map((key) => (
              <ToggleGroupItem
                key={key}
                text={key === '7d' ? '7 days' : key === '30d' ? '30 days' : '90 days'}
                isSelected={range === key}
                onChange={() => setRange(key)}
              />
            ))}
          </ToggleGroup>
          <FormSelect
            id="usage-project-filter"
            value={projectId}
            onChange={(_e, v) => setProjectId(v)}
            aria-label="Filter by project"
            className="usage-project-select"
          >
            <FormSelectOption value="" label="All projects" />
            {projects.map((p) => (
              <FormSelectOption key={p.id} value={p.id} label={p.name} />
            ))}
          </FormSelect>
        </div>
      </PageSection>

      <PageSection isFilled className="usage-body-section" aria-label="Usage dashboard">
        {demoMode ? (
          <EmptyState
            variant={EmptyStateVariant.lg}
            titleText="Demo mode"
            headingLevel="h2"
            icon={ChartLineIcon}
          >
            <EmptyStateBody>
              Usage analytics are unavailable in demo mode. Sign in and send chat
              messages to start collecting real token metrics.
            </EmptyStateBody>
          </EmptyState>
        ) : !org?.id ? (
          <EmptyState
            variant={EmptyStateVariant.lg}
            titleText="No organization"
            headingLevel="h2"
            icon={ChartLineIcon}
          >
            <EmptyStateBody>Select an organization to view usage.</EmptyStateBody>
          </EmptyState>
        ) : loading && !summary ? (
          <div className="usage-loading">
            <Spinner aria-label="Loading usage" />
          </div>
        ) : error ? (
          <EmptyState
            variant={EmptyStateVariant.lg}
            titleText="Could not load usage"
            headingLevel="h2"
            icon={ChartLineIcon}
          >
            <EmptyStateBody>{error}</EmptyStateBody>
          </EmptyState>
        ) : empty ? (
          <EmptyState
            variant={EmptyStateVariant.lg}
            titleText="No usage yet"
            headingLevel="h2"
            icon={ChartLineIcon}
          >
            <EmptyStateBody>
              No AI usage recorded for this range yet. Send chats in a project to
              start collecting usage.
            </EmptyStateBody>
          </EmptyState>
        ) : summary ? (
          <div className="usage-dashboard">
            <div className="usage-kpis">
              <div className="usage-kpi">
                <span className="usage-kpi-label">Total tokens</span>
                <span className="usage-kpi-value">
                  {formatTokens(summary.totals.total_tokens)}
                </span>
                <span className="usage-kpi-sub">
                  {formatTokens(summary.totals.input_tokens)} in ·{' '}
                  {formatTokens(summary.totals.output_tokens)} out
                </span>
              </div>
              <div className="usage-kpi">
                <span className="usage-kpi-label">Chat turns</span>
                <span className="usage-kpi-value">{summary.totals.messages}</span>
                <span className="usage-kpi-sub">Completed assistant replies</span>
              </div>
              <div className="usage-kpi">
                <span className="usage-kpi-label">Sessions</span>
                <span className="usage-kpi-value">{summary.totals.sessions}</span>
                <span className="usage-kpi-sub">OpenCode chat sessions</span>
              </div>
              <div className="usage-kpi">
                <span className="usage-kpi-label">
                  {scope === 'org' ? 'Active users' : 'Projects'}
                </span>
                <span className="usage-kpi-value">
                  {scope === 'org' ? summary.totals.users : summary.totals.projects}
                </span>
                <span className="usage-kpi-sub">
                  {scope === 'org'
                    ? `${summary.totals.projects} projects`
                    : 'With recorded usage'}
                </span>
              </div>
            </div>

            <div className="usage-charts">
              <section className="usage-chart-card" aria-label="Tokens over time">
                <h2 className="usage-chart-title">Tokens over time</h2>
                <div className="usage-chart-canvas">
                  {seriesTokens.length === 0 ? (
                    <p className="usage-chart-empty">No series data</p>
                  ) : (
                    <Chart
                      ariaDesc="Daily AI token usage"
                      ariaTitle="Tokens over time"
                      containerComponent={
                        <ChartVoronoiContainer
                          labels={({ datum }) => `${datum.x}: ${formatTokens(datum.y)} tokens`}
                          constrainToVisibleArea
                        />
                      }
                      height={240}
                      padding={{ bottom: 50, left: 60, right: 20, top: 20 }}
                      themeColor={ChartThemeColor.blue}
                      width={700}
                    >
                      <ChartAxis
                        tickValues={seriesTokens.map((d) => d.x).filter((_, i) => {
                          const step = Math.max(1, Math.ceil(seriesTokens.length / 7))
                          return i % step === 0
                        })}
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartAxis
                        dependentAxis
                        showGrid
                        tickFormat={(t: number) => formatTokens(Number(t))}
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartGroup>
                        <ChartLine data={seriesTokens} />
                      </ChartGroup>
                    </Chart>
                  )}
                </div>
              </section>

              <section className="usage-chart-card" aria-label="Turns over time">
                <h2 className="usage-chart-title">Chat turns over time</h2>
                <div className="usage-chart-canvas">
                  {seriesMessages.length === 0 ? (
                    <p className="usage-chart-empty">No series data</p>
                  ) : (
                    <Chart
                      ariaDesc="Daily chat turn count"
                      ariaTitle="Chat turns over time"
                      containerComponent={
                        <ChartVoronoiContainer
                          labels={({ datum }) => `${datum.x}: ${datum.y} turns`}
                          constrainToVisibleArea
                        />
                      }
                      height={240}
                      padding={{ bottom: 50, left: 50, right: 20, top: 20 }}
                      themeColor={ChartThemeColor.green}
                      width={700}
                    >
                      <ChartAxis
                        tickValues={seriesMessages.map((d) => d.x).filter((_, i) => {
                          const step = Math.max(1, Math.ceil(seriesMessages.length / 7))
                          return i % step === 0
                        })}
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartAxis
                        dependentAxis
                        showGrid
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartGroup>
                        <ChartLine data={seriesMessages} />
                      </ChartGroup>
                    </Chart>
                  )}
                </div>
              </section>

              <section className="usage-chart-card" aria-label="Tokens by model">
                <h2 className="usage-chart-title">By model</h2>
                <div className="usage-chart-canvas usage-chart-canvas--bar">
                  {byModel.length === 0 ? (
                    <p className="usage-chart-empty">No model breakdown</p>
                  ) : (
                    <Chart
                      ariaDesc="Tokens by model"
                      ariaTitle="By model"
                      domainPadding={{ x: [20, 20] }}
                      height={Math.max(200, byModel.length * 36)}
                      padding={{ bottom: 40, left: 140, right: 30, top: 16 }}
                      themeColor={ChartThemeColor.multiOrdered}
                      width={700}
                    >
                      <ChartAxis style={{ tickLabels: { fontSize: 10 } }} />
                      <ChartAxis
                        dependentAxis
                        showGrid
                        tickFormat={(t: number) => formatTokens(Number(t))}
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartBar
                        horizontal
                        data={byModel}
                        labels={({ datum }) => formatTokens(datum.y)}
                      />
                    </Chart>
                  )}
                </div>
              </section>

              <section className="usage-chart-card" aria-label="Tokens by project">
                <h2 className="usage-chart-title">By project</h2>
                <div className="usage-chart-canvas usage-chart-canvas--bar">
                  {byProject.length === 0 ? (
                    <p className="usage-chart-empty">No project breakdown</p>
                  ) : (
                    <Chart
                      ariaDesc="Tokens by project"
                      ariaTitle="By project"
                      domainPadding={{ x: [20, 20] }}
                      height={Math.max(200, byProject.length * 36)}
                      padding={{ bottom: 40, left: 120, right: 30, top: 16 }}
                      themeColor={ChartThemeColor.purple}
                      width={700}
                    >
                      <ChartAxis style={{ tickLabels: { fontSize: 10 } }} />
                      <ChartAxis
                        dependentAxis
                        showGrid
                        tickFormat={(t: number) => formatTokens(Number(t))}
                        style={{ tickLabels: { fontSize: 10 } }}
                      />
                      <ChartBar
                        horizontal
                        data={byProject}
                        labels={({ datum }) => formatTokens(datum.y)}
                      />
                    </Chart>
                  )}
                </div>
              </section>

              {scope === 'org' ? (
                <section
                  className="usage-chart-card usage-chart-card--wide"
                  aria-label="Tokens by member"
                >
                  <h2 className="usage-chart-title">By member</h2>
                  <div className="usage-chart-canvas usage-chart-canvas--bar">
                    {byUser.length === 0 ? (
                      <p className="usage-chart-empty">No member breakdown</p>
                    ) : (
                      <>
                        <Chart
                          ariaDesc="Tokens by organization member"
                          ariaTitle="By member"
                          domainPadding={{ x: [20, 20] }}
                          height={Math.max(200, byUser.length * 36)}
                          padding={{ bottom: 40, left: 100, right: 30, top: 16 }}
                          themeColor={ChartThemeColor.orange}
                          width={700}
                        >
                          <ChartAxis style={{ tickLabels: { fontSize: 10 } }} />
                          <ChartAxis
                            dependentAxis
                            showGrid
                            tickFormat={(t: number) => formatTokens(Number(t))}
                            style={{ tickLabels: { fontSize: 10 } }}
                          />
                          <ChartBar
                            horizontal
                            data={byUser}
                            labels={({ datum }) => formatTokens(datum.y)}
                          />
                        </Chart>
                        <table className="usage-member-table">
                          <thead>
                            <tr>
                              <th scope="col">Member</th>
                              <th scope="col">Tokens</th>
                              <th scope="col">Turns</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(summary.by_user || []).map((u) => (
                              <tr key={u.user_id}>
                                <td>{u.email}</td>
                                <td>{formatTokens(u.tokens)}</td>
                                <td>{u.messages}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    )}
                  </div>
                </section>
              ) : null}
            </div>
            {loading ? (
              <div className="usage-refreshing" aria-live="polite">
                <Spinner size="md" aria-label="Refreshing usage" />
              </div>
            ) : null}
          </div>
        ) : null}
      </PageSection>
    </>
  )
}
