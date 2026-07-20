import { useMemo, useState } from 'react'
import { Button, ExpandableSection, SearchInput } from '@patternfly/react-core'
import { SplitWorkbench } from '@/components/studio/SplitWorkbench'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { SqlResult } from '@/types/studio'

export function DatabasePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const state = useProjectStudio(projectId)
  const runSql = useStudioDemoStore((s) => s.runSql)

  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(state.tables[0]?.name ?? '')
  const [sql, setSql] = useState(state.sqlDefault)
  const [result, setResult] = useState<SqlResult | null>(null)
  const [migOpen, setMigOpen] = useState(false)

  const tables = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return state.tables
    return state.tables.filter((t) => t.name.toLowerCase().includes(needle))
  }, [state.tables, q])

  const onSelectTable = (name: string) => {
    setSelected(name)
    setSql(`SELECT * FROM ${name} LIMIT 100;`)
  }

  const onRun = () => {
    setResult(runSql(projectId, sql))
  }

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
          title={state.dbConn}
        >
          {state.dbConn}
        </span>
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
          </>
        }
        main={
          <>
            <div className="db-sql-toolbar">
              <Button variant="primary" size="sm" onClick={onRun}>
                Run
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setSql('')}>
                Clear
              </Button>
              <span className="lc-meta">Demo SQL engine — not a live database connection</span>
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
                  onRun()
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
