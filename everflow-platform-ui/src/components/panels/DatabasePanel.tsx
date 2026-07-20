import { useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { getStudioExtras } from '@/data/studioExtras'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function DatabasePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const d = getStudioExtras(projectId)
  const [sub, setSub] = useState<'tables' | 'sql' | 'migrations'>('tables')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="tables" title={<TabTitleText>Tables</TabTitleText>} />
          <Tab eventKey="sql" title={<TabTitleText>SQL</TabTitleText>} />
          <Tab eventKey="migrations" title={<TabTitleText>Migrations</TabTitleText>} />
        </Tabs>
        <span
          className="pill"
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 10.5,
            maxWidth: 220,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={d.dbConn}
        >
          {d.dbConn}
        </span>
      </div>
      <div className="panel-scroll">
        {sub === 'tables' &&
          d.tables.map((t) => (
            <div className="list-card" key={t.name}>
              <div className="lc-row">
                <div className="lc-title" style={{ fontFamily: 'var(--mono)' }}>
                  {t.name}
                </div>
                <span className="lc-meta">
                  {t.rows} rows · {t.size}
                </span>
              </div>
            </div>
          ))}
        {sub === 'sql' && (
          <>
            <pre
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 12,
                padding: 12,
                background: 'var(--pf-t--global--background--color--secondary--default)',
                borderRadius: 6,
                whiteSpace: 'pre-wrap',
              }}
            >
              {d.sqlDefault}
            </pre>
            <table className="sql-table">
              <tbody>
                {d.sqlRows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell) => (
                      <td key={cell}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {sub === 'migrations' && (
          <div className="list-card">
            <div className="lc-title">001_init.sql</div>
            <div className="lc-meta">applied · demo</div>
          </div>
        )}
      </div>
    </div>
  )
}
