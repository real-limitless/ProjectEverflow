import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, ExpandableSection, SearchInput, Spinner } from '@patternfly/react-core'
import { SplitWorkbench } from '@/components/studio/SplitWorkbench'
import { getProject } from '@/data/projects'
import { isDemoMode } from '@/lib/api'
import {
  getDatabaseStatus,
  listDatabaseTables,
  runDatabaseQuery,
  type ApiDatabaseStatus,
  type ApiDatabaseTable,
} from '@/lib/databaseApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { DbTable, SqlResult } from '@/types/studio'

function apiTableToDbTable(t: ApiDatabaseTable): DbTable {
  return {
    name: t.schema_name && t.schema_name !== 'public' ? `${t.schema_name}.${t.name}` : t.name,
    rows: t.rows ?? 0,
    size: t.size ?? '—',
  }
}

export function DatabasePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const useApi = Boolean(project?.fromApi) && !isDemoMode()
  const sandboxRunning = project?.sandboxStatus === 'running'

  const state = useProjectStudio(projectId)
  const runSql = useStudioDemoStore((s) => s.runSql)

  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(state.tables[0]?.name ?? '')
  const [sql, setSql] = useState(state.sqlDefault)
  const [result, setResult] = useState<SqlResult | null>(null)
  const [migOpen, setMigOpen] = useState(false)

  const [apiStatus, setApiStatus] = useState<ApiDatabaseStatus | null>(null)
  const [apiTables, setApiTables] = useState<DbTable[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const refreshApi = useCallback(async () => {
    if (!useApi || !projectId) return
    if (!sandboxRunning) {
      setApiStatus({
        status: 'no_sandbox',
        psql_available: false,
        harness_installed: false,
        message: 'Sandbox is not running.',
      })
      setApiTables([])
      return
    }
    setLoadError(null)
    try {
      const [status, tablesRes] = await Promise.all([
        getDatabaseStatus(projectId),
        listDatabaseTables(projectId).catch(() => null),
      ])
      setApiStatus(status)
      if (tablesRes?.tables) {
        const mapped = tablesRes.tables.map(apiTableToDbTable)
        setApiTables(mapped)
        setSelected((prev) => {
          if (prev && mapped.some((t) => t.name === prev)) return prev
          return mapped[0]?.name ?? ''
        })
      } else {
        setApiTables([])
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Failed to load database status')
      setApiTables([])
    }
  }, [useApi, projectId, sandboxRunning])

  useEffect(() => {
    if (!useApi) return
    setLoading(true)
    void refreshApi().finally(() => setLoading(false))
  }, [useApi, refreshApi])

  const sourceTables = useApi ? apiTables : state.tables
  const dbConn = useApi
    ? apiStatus?.display_url || apiStatus?.message || '—'
    : state.dbConn

  const tables = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return sourceTables
    return sourceTables.filter((t) => t.name.toLowerCase().includes(needle))
  }, [sourceTables, q])

  const onSelectTable = (name: string) => {
    setSelected(name)
    const bare = name.includes('.') ? name.split('.').slice(1).join('.') : name
    const ident = name.includes('.') ? `"${name.split('.')[0]}"."${bare}"` : name
    setSql(`SELECT * FROM ${ident} LIMIT 100;`)
  }

  const onRun = async () => {
    if (useApi) {
      if (!projectId || !sandboxRunning) {
        setResult({ columns: [], rows: [], error: 'Sandbox is not running' })
        return
      }
      setRunning(true)
      try {
        const res = await runDatabaseQuery(projectId, { sql, limit: 100 })
        setResult({
          columns: res.columns,
          rows: res.rows,
          rowCount: res.row_count,
          error: res.error ?? undefined,
        })
      } catch (e) {
        setResult({
          columns: [],
          rows: [],
          error: e instanceof Error ? e.message : 'Query failed',
        })
      } finally {
        setRunning(false)
      }
      return
    }
    setResult(runSql(projectId, sql))
  }

  const statusHint = useApi
    ? apiStatus?.status === 'ready'
      ? null
      : apiStatus?.message ||
        (apiStatus?.status === 'not_provisioned'
          ? 'Database not provisioned. Set DATABASE_URL in .everflow/database.json or start Postgres.'
          : null)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          SQL workbench
        </span>
        <span
          className="pill"
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 10.5,
            maxWidth: 260,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={dbConn}
        >
          {dbConn}
        </span>
        {useApi && (
          <Button variant="secondary" size="sm" onClick={() => void refreshApi()} isDisabled={loading}>
            {loading ? <Spinner size="sm" aria-label="Loading" /> : 'Refresh'}
          </Button>
        )}
      </div>
      <SplitWorkbench
        sidebar={
          <>
            <div style={{ padding: '0.5rem' }}>
              <SearchInput
                placeholder="Tables…"
                value={q}
                onChange={(_e, v) => setQ(v)}
                onClear={() => setQ('')}
              />
            </div>
            <div className="section-label" style={{ paddingInline: '0.75rem' }}>
              Tables
            </div>
            {useApi && loading && tables.length === 0 && (
              <div className="lc-meta" style={{ padding: '0.5rem 0.75rem' }}>
                Loading…
              </div>
            )}
            {useApi && !loading && tables.length === 0 && (
              <div className="lc-meta" style={{ padding: '0.5rem 0.75rem' }}>
                {loadError || statusHint || 'No tables (connection not ready).'}
              </div>
            )}
            {tables.map((t) => (
              <div
                key={t.name}
                className={`db-table-item ${selected === t.name ? 'is-active' : ''}`}
                onClick={() => onSelectTable(t.name)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSelectTable(t.name)
                }}
              >
                {t.name}
                <div className="meta">
                  {t.rows.toLocaleString()} rows · {t.size}
                </div>
              </div>
            ))}
            {!useApi && (
              <div style={{ marginTop: 'auto', padding: '0.5rem' }}>
                <ExpandableSection
                  toggleText="Schema / migrations"
                  isExpanded={migOpen}
                  onToggle={(_e, v) => setMigOpen(v)}
                >
                  {state.migrations.map((m) => (
                    <div key={m.name} className="lc-meta" style={{ marginBottom: 4, fontFamily: 'var(--mono)' }}>
                      {m.name} · {m.status}
                    </div>
                  ))}
                </ExpandableSection>
              </div>
            )}
            {useApi && statusHint && tables.length > 0 && (
              <div className="lc-meta" style={{ marginTop: 'auto', padding: '0.5rem 0.75rem' }}>
                {statusHint}
              </div>
            )}
          </>
        }
        main={
          <>
            <div className="db-sql-toolbar">
              <Button variant="primary" size="sm" onClick={() => void onRun()} isDisabled={running}>
                {running ? 'Running…' : 'Run'}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setSql('')}>
                Clear
              </Button>
              {!useApi && (
                <span className="lc-meta">Demo SQL engine — not a live database connection</span>
              )}
              {useApi && apiStatus?.status && apiStatus.status !== 'ready' && (
                <span className="lc-meta">{apiStatus.status}</span>
              )}
              {useApi && apiStatus?.status === 'ready' && (
                <span className="lc-meta">Live · read-only SELECT</span>
              )}
            </div>
            <textarea
              className="db-sql-editor"
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              spellCheck={false}
              aria-label="SQL editor"
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                  e.preventDefault()
                  void onRun()
                }
              }}
            />
          </>
        }
        results={
          <div style={{ padding: '0.5rem 0.75rem' }}>
            <div className="section-label" style={{ marginTop: 0 }}>
              Results
              {result?.rowCount != null && !result.error ? ` · ${result.rowCount} rows` : ''}
            </div>
            {!result && <div className="lc-meta">Run a query to see results.</div>}
            {result?.error && (
              <div style={{ color: 'var(--pf-t--global--text--color--status--danger--default)' }}>
                {result.error}
              </div>
            )}
            {result && !result.error && result.columns.length > 0 && (
              <table className="sql-table">
                <thead>
                  <tr>
                    {result.columns.map((c) => (
                      <th key={c} style={{ textAlign: 'left', padding: '0.25rem 0.5rem' }}>
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        }
      />
    </div>
  )
}
