import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, FormSelect, FormSelectOption, Spinner, TextInput } from '@patternfly/react-core'
import { isDemoMode } from '@/lib/api'
import {
  attachSeat,
  ensureOrg,
  exportOrgYaml,
  fireSeat,
  getChart,
  hireSeat,
  listRuns,
  pauseSeat,
  reparentSeat,
  resumeSeat,
} from '@/lib/orgApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { ChartSnapshot, OrgRun, Seat } from '@/types/org'

export function ChartPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const setSurfaceMode = usePlaygroundStore((s) => s.setSurfaceMode)
  const [chart, setChart] = useState<ChartSnapshot | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runs, setRuns] = useState<OrgRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hireName, setHireName] = useState('Intern')
  const [hireTemplate, setHireTemplate] = useState('scout')
  const [yaml, setYaml] = useState<string | null>(null)

  const selected = chart?.seats.find((s) => s.id === selectedId) || null
  const byId = useMemo(
    () => Object.fromEntries((chart?.seats || []).map((s) => [s.id, s])),
    [chart],
  )
  const activeRun = runs[0]
  const pathSlugs = new Set(
    (activeRun?.nodes || [])
      .map((n) => {
        const seat = chart?.seats.find((s) => s.id === n.seat_id)
        return seat?.slug
      })
      .filter(Boolean) as string[],
  )

  const refresh = useCallback(async () => {
    if (!projectId || isDemoMode()) {
      setLoading(false)
      return
    }
    try {
      const snap = await getChart(projectId)
      setChart(snap)
      setRuns(await listRuns(projectId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Chart failed')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const act = async (fn: () => Promise<unknown>) => {
    if (!projectId) return
    try {
      await fn()
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }

  if (!projectId) return <div className="room-empty">Open a project to use the org chart.</div>
  if (isDemoMode()) {
    return <div className="room-empty">Chart needs a live API project.</div>
  }
  if (loading) {
    return (
      <div className="room-empty">
        <Spinner size="lg" />
      </div>
    )
  }

  const line = (chart?.seats || []).filter((s) => s.lane === 'line')
  const services = (chart?.seats || []).filter((s) => s.lane === 'services')

  return (
    <div className="chart-layout">
      <div className="chart-canvas">
        <header className="chart-head">
          <h2>Org chart</h2>
          <p>Reporting lines are permission lines. A live run lights the path.</p>
          <div className="chart-head__actions">
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                void act(async () => {
                  if (projectId) setChart(await ensureOrg(projectId))
                })
              }
            >
              Ensure starter
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                void (async () => {
                  if (projectId) setYaml(await exportOrgYaml(projectId))
                })()
              }
            >
              Export yaml
            </Button>
          </div>
        </header>
        {error ? <div className="room-error">{error}</div> : null}
        <div className="chart-tree">
          {line.map((s) => (
            <SeatCard
              key={s.id}
              seat={s}
              parent={s.reports_to_id ? byId[s.reports_to_id] : undefined}
              lit={pathSlugs.has(s.slug)}
              selected={s.id === selectedId}
              onSelect={() => setSelectedId(s.id)}
            />
          ))}
        </div>
        <div className="chart-services">
          <div className="room-rail__title">Services lane</div>
          <div className="chart-tree chart-tree--services">
            {services.map((s) => (
              <SeatCard
                key={s.id}
                seat={s}
                parent={s.reports_to_id ? byId[s.reports_to_id] : undefined}
                lit={pathSlugs.has(s.slug)}
                selected={s.id === selectedId}
                onSelect={() => setSelectedId(s.id)}
              />
            ))}
          </div>
        </div>
        {yaml ? <pre className="chart-yaml">{yaml}</pre> : null}
      </div>

      <aside className="chart-inspector" aria-label="Seat inspector">
        {selected ? (
          <>
            <h3>{selected.name}</h3>
            <p className="chart-inspector__meta">
              {selected.kind} · {selected.role} · {selected.status}
              {selected.paused ? ' · paused' : ''}
            </p>
            <p>{selected.description}</p>
            <div className="chart-chips">
              {(selected.tools || []).map((t) => (
                <span key={t} className="chart-chip">
                  {t}
                </span>
              ))}
            </div>
            <dl className="chart-dl">
              <dt>Model / agent</dt>
              <dd>{selected.agent_slug || '—'}</dd>
              <dt>Session</dt>
              <dd>{selected.opencode_session_id || 'not attached'}</dd>
              <dt>Worktree</dt>
              <dd>{selected.worktree_path || '—'}</dd>
              <dt>Reports to</dt>
              <dd>{selected.reports_to_id ? byId[selected.reports_to_id]?.name : '—'}</dd>
            </dl>
            <div className="chart-inspector__btns">
              <Button size="sm" onClick={() => setSurfaceMode('room')}>
                Open room
              </Button>
              {selected.kind === 'bot' ? (
                <>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void act(async () => {
                        if (projectId) await attachSeat(projectId, selected.id)
                        setSurfaceMode('harness')
                      })
                    }
                  >
                    Attach harness
                  </Button>
                  {selected.paused ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void act(() => resumeSeat(projectId, selected.id))}
                    >
                      Resume
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void act(() => pauseSeat(projectId, selected.id))}
                    >
                      Pause
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => void act(() => fireSeat(projectId, selected.id))}
                  >
                    Fire
                  </Button>
                </>
              ) : null}
            </div>
            {selected.kind === 'bot' && chart ? (
              <label className="chart-reparent">
                Reparent
                <FormSelect
                  value={selected.reports_to_id || ''}
                  onChange={(_e, v) =>
                    void act(() => reparentSeat(projectId, selected.id, v || null))
                  }
                  aria-label="Reports to"
                >
                  <FormSelectOption value="" label="(none)" />
                  {chart.seats
                    .filter((s) => s.id !== selected.id && !s.fired)
                    .map((s) => (
                      <FormSelectOption key={s.id} value={s.id} label={s.name} />
                    ))}
                </FormSelect>
              </label>
            ) : null}
          </>
        ) : (
          <p>Select a seat. Hire, pause, fire, or attach its harness.</p>
        )}

        <div className="chart-hire">
          <div className="room-rail__title">Hire</div>
          <TextInput
            value={hireName}
            onChange={(_e, v) => setHireName(v)}
            aria-label="New seat name"
          />
          <FormSelect
            value={hireTemplate}
            onChange={(_e, v) => setHireTemplate(v)}
            aria-label="Template"
          >
            {['scout', 'docs', 'sec', 'scribe', 'product', 'qa'].map((t) => (
              <FormSelectOption key={t} value={t} label={t} />
            ))}
          </FormSelect>
          <Button
            size="sm"
            onClick={() =>
              void act(async () => {
                const slug = hireName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
                await hireSeat(projectId, {
                  name: hireName,
                  slug: slug || `hire-${Date.now()}`,
                  template: hireTemplate,
                  kind: 'bot',
                })
              })
            }
          >
            Hire seat
          </Button>
        </div>
      </aside>
    </div>
  )
}

function SeatCard({
  seat,
  parent,
  lit,
  selected,
  onSelect,
}: {
  seat: Seat
  parent?: Seat
  lit: boolean
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={`seat-card${seat.kind === 'bot' ? ' is-bot' : ' is-human'}${lit ? ' is-lit' : ''}${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
    >
      <span className="seat-card__name">{seat.name}</span>
      <span className="seat-card__role">{seat.role}</span>
      {parent ? <span className="seat-card__reports">→ {parent.name}</span> : null}
    </button>
  )
}
