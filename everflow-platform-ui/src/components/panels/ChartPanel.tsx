import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  FormSelect,
  FormSelectOption,
  Spinner,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { isDemoMode } from '@/lib/api'
import { CHAT_MODELS, type CatalogItem } from '@/data/chatCatalog'
import { OPENCODE_TOOL_PERMISSIONS } from '@/lib/harness/opencodePack'
import { listProviders } from '@/lib/opencode/client'
import {
  addSeat,
  attachSeat,
  createTeam,
  deleteTeam,
  ensureOrg,
  exportOrgYaml,
  getChart,
  listRuns,
  listTeams,
  pauseSeat,
  removeSeat,
  resumeSeat,
  updateSeat,
} from '@/lib/orgApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { ChartSnapshot, OrgRun, Seat, Team } from '@/types/org'
import { ModelBrowseModal } from './ModelBrowseModal'

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function ChartPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const [chart, setChart] = useState<ChartSnapshot | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [runs, setRuns] = useState<OrgRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showSystem, setShowSystem] = useState(false)
  const [yaml, setYaml] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [addName, setAddName] = useState('Scout')
  const [addTemplate, setAddTemplate] = useState('scout')
  const [addTeamId, setAddTeamId] = useState('')
  const [addReportsTo, setAddReportsTo] = useState('')
  const [teamName, setTeamName] = useState('')

  const refresh = useCallback(async () => {
    if (!projectId || isDemoMode()) {
      setLoading(false)
      return
    }
    try {
      const [snap, tm] = await Promise.all([
        // Always load Floor so hidden conductors can be skipped without flattening the tree.
        getChart(projectId, { includeSystem: true }),
        listTeams(projectId),
      ])
      setChart(snap)
      setTeams(tm)
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
      setError(null)
      await fn()
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }

  const visibleSeats = useMemo(() => {
    const seats = chart?.seats || []
    if (showSystem) return seats
    return seats.filter((s) => !s.is_conductor)
  }, [chart, showSystem])

  const visibleIds = useMemo(() => new Set(visibleSeats.map((s) => s.id)), [visibleSeats])

  const parentOf = useCallback(
    (seat: Seat): string | null => {
      const all = Object.fromEntries((chart?.seats || []).map((s) => [s.id, s]))
      const seen = new Set<string>()
      let cur = seat.reports_to_id
      while (cur) {
        if (seen.has(cur)) return null
        seen.add(cur)
        if (visibleIds.has(cur)) return cur
        cur = all[cur]?.reports_to_id || null
      }
      return null
    },
    [chart, visibleIds],
  )

  const roots = useMemo(
    () => visibleSeats.filter((s) => !parentOf(s)),
    [visibleSeats, parentOf],
  )

  const childrenOf = useCallback(
    (id: string) => visibleSeats.filter((s) => parentOf(s) === id),
    [visibleSeats, parentOf],
  )

  useEffect(() => {
    if (addReportsTo) return
    const human = visibleSeats.find((s) => s.kind === 'human')
    if (human) setAddReportsTo(human.id)
  }, [visibleSeats, addReportsTo])

  const selected = visibleSeats.find((s) => s.id === selectedId) || null
  const byId = useMemo(
    () => Object.fromEntries((chart?.seats || []).map((s) => [s.id, s])),
    [chart],
  )
  const pathSlugs = new Set(
    (runs[0]?.nodes || [])
      .map((n) => chart?.seats.find((s) => s.id === n.seat_id)?.slug)
      .filter(Boolean) as string[],
  )

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

  return (
    <div className="chart-layout">
      <div className="chart-canvas">
        <header className="chart-head">
          <h2>Org chart</h2>
          <p>Reporting lines. A live run lights the path. Select a bot to configure it.</p>
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
            <Button size="sm" onClick={() => setAdding((v) => !v)}>
              Add seat
            </Button>
            <Checkbox
              id="show-system-seats"
              label="Show system seats"
              isChecked={showSystem}
              onChange={(_e, v) => setShowSystem(v)}
            />
          </div>
        </header>
        {error ? <div className="room-error">{error}</div> : null}
        {adding ? (
          <div className="chart-add">
            <TextInput value={addName} onChange={(_e, v) => setAddName(v)} aria-label="New seat name" />
            <FormSelect value={addTemplate} onChange={(_e, v) => setAddTemplate(v)} aria-label="Template">
              {['scout', 'docs', 'sec', 'scribe', 'product', 'qa'].map((t) => (
                <FormSelectOption key={t} value={t} label={t} />
              ))}
            </FormSelect>
            <FormSelect value={addTeamId} onChange={(_e, v) => setAddTeamId(v)} aria-label="Team">
              <FormSelectOption value="" label="No team" />
              {teams.map((t) => (
                <FormSelectOption key={t.id} value={t.id} label={`@${t.mention}`} />
              ))}
            </FormSelect>
            <FormSelect value={addReportsTo} onChange={(_e, v) => setAddReportsTo(v)} aria-label="Reports to">
              <FormSelectOption value="" label="Reports to (none)" />
              {visibleSeats.map((s) => (
                <FormSelectOption key={s.id} value={s.id} label={s.name} />
              ))}
            </FormSelect>
            <Button
              size="sm"
              onClick={() =>
                void act(async () => {
                  await addSeat(projectId, {
                    name: addName,
                    slug: slugify(addName) || `seat-${Date.now()}`,
                    template: addTemplate,
                    kind: 'bot',
                    team_id: addTeamId || null,
                    reports_to_id: addReportsTo || null,
                  })
                  setAdding(false)
                })
              }
            >
              Add
            </Button>
          </div>
        ) : null}

        <div className="org-tree" role="tree" aria-label="Organization chart">
          {roots.map((s) => (
            <OrgBranch
              key={s.id}
              seat={s}
              childrenOf={childrenOf}
              teams={teams}
              pathSlugs={pathSlugs}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ))}
        </div>

        <div className="chart-teams">
          <div className="room-rail__title">Teams</div>
          <ul className="chart-teams__list">
            {teams.map((t) => (
              <li key={t.id}>
                <span>@{t.mention}</span>
                <Button
                  size="sm"
                  variant="plain"
                  onClick={() => void act(() => deleteTeam(projectId, t.id))}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
          <div className="chart-add chart-add--inline">
            <TextInput
              value={teamName}
              onChange={(_e, v) => setTeamName(v)}
              aria-label="New team name"
              placeholder="New team"
            />
            <Button
              size="sm"
              onClick={() =>
                void act(async () => {
                  const slug = slugify(teamName)
                  if (!slug) return
                  await createTeam(projectId, { name: teamName, slug, mention: slug })
                  setTeamName('')
                })
              }
            >
              Add team
            </Button>
          </div>
        </div>
        {yaml ? <pre className="chart-yaml">{yaml}</pre> : null}
      </div>

      <aside className="chart-inspector" aria-label="Seat inspector">
        {selected ? (
          <SeatInspector
            seat={selected}
            seats={visibleSeats}
            teams={teams}
            byId={byId}
            onSave={(body) => act(() => updateSeat(projectId, selected.id, body))}
            onOpenRoom={() => openPanelType('room')}
            onOpenSession={() =>
              void act(async () => {
                if (selected.kind === 'bot') await attachSeat(projectId, selected.id)
                openPanelType('terminal')
              })
            }
            onPause={() => act(() => pauseSeat(projectId, selected.id))}
            onResume={() => act(() => resumeSeat(projectId, selected.id))}
            onRemove={() =>
              act(async () => {
                await removeSeat(projectId, selected.id)
                setSelectedId(null)
              })
            }
          />
        ) : (
          <p>Select a seat to set job, prompt, tools, skills, and model pool.</p>
        )}
      </aside>
    </div>
  )
}

function OrgBranch({
  seat,
  childrenOf,
  teams,
  pathSlugs,
  selectedId,
  onSelect,
}: {
  seat: Seat
  childrenOf: (id: string) => Seat[]
  teams: Team[]
  pathSlugs: Set<string>
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const kids = childrenOf(seat.id)
  const team = teams.find((t) => t.id === seat.team_id)
  return (
    <div className="org-branch" role="treeitem" aria-expanded={kids.length > 0}>
      <SeatCard
        seat={seat}
        team={team}
        lit={pathSlugs.has(seat.slug)}
        selected={seat.id === selectedId}
        onSelect={() => onSelect(seat.id)}
      />
      {kids.length > 0 ? (
        <div className="org-kids" role="group">
          {kids.map((child) => (
            <OrgBranch
              key={child.id}
              seat={child}
              childrenOf={childrenOf}
              teams={teams}
              pathSlugs={pathSlugs}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function SeatCard({
  seat,
  team,
  lit,
  selected,
  onSelect,
}: {
  seat: Seat
  team?: Team
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
      {team ? <span className="seat-card__team">@{team.mention}</span> : null}
    </button>
  )
}

function SeatInspector({
  seat,
  seats,
  teams,
  byId,
  onSave,
  onOpenRoom,
  onOpenSession,
  onPause,
  onResume,
  onRemove,
}: {
  seat: Seat
  seats: Seat[]
  teams: Team[]
  byId: Record<string, Seat>
  onSave: (body: Parameters<typeof updateSeat>[2]) => Promise<void>
  onOpenRoom: () => void
  onOpenSession: () => void
  onPause: () => Promise<void>
  onResume: () => Promise<void>
  onRemove: () => Promise<void>
}) {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const [description, setDescription] = useState(seat.description)
  const [prompt, setPrompt] = useState(seat.prompt || '')
  const [skills, setSkills] = useState((seat.skills || []).join(', '))
  const [models, setModels] = useState((seat.preferred_models || []).join(', '))
  const [tools, setTools] = useState<string[]>(seat.tools || [])
  const [permission, setPermission] = useState<Record<string, string>>(seat.permission || {})
  const [teamId, setTeamId] = useState(seat.team_id || '')
  const [reportsTo, setReportsTo] = useState(seat.reports_to_id || '')
  const [browseOpen, setBrowseOpen] = useState(false)
  const [catalog, setCatalog] = useState<CatalogItem[]>(CHAT_MODELS)

  useEffect(() => {
    setDescription(seat.description)
    setPrompt(seat.prompt || '')
    setSkills((seat.skills || []).join(', '))
    setModels((seat.preferred_models || []).join(', '))
    setTools(seat.tools || [])
    setPermission(seat.permission || {})
    setTeamId(seat.team_id || '')
    setReportsTo(seat.reports_to_id || '')
  }, [seat])

  useEffect(() => {
    if (!projectId) return
    void listProviders(projectId)
      .then((prov) => {
        const items: CatalogItem[] = []
        for (const pvd of prov.providers || []) {
          const modelsRaw = pvd.models
          if (Array.isArray(modelsRaw)) {
            for (const m of modelsRaw as { id: string; name?: string }[]) {
              items.push({
                id: `${pvd.id}/${m.id}`,
                label: m.name || m.id,
                description: pvd.name || pvd.id,
              })
            }
          } else if (modelsRaw && typeof modelsRaw === 'object') {
            for (const [mid, meta] of Object.entries(
              modelsRaw as Record<string, { name?: string }>,
            )) {
              items.push({
                id: `${pvd.id}/${mid}`,
                label: meta?.name || mid,
                description: pvd.name || pvd.id,
              })
            }
          }
        }
        if (items.length) setCatalog(items)
      })
      .catch(() => {
        setCatalog(CHAT_MODELS)
      })
  }, [projectId])

  const split = (raw: string) =>
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

  return (
    <>
      <h3>{seat.name}</h3>
      <p className="chart-inspector__meta">
        {seat.kind} · {seat.role} · {seat.status}
        {seat.paused ? ' · paused' : ''}
        {byId[seat.reports_to_id || ''] ? ` · reports to ${byId[seat.reports_to_id || ''].name}` : ''}
      </p>

      <label className="chart-field">
        Job responsibilities
        <TextArea value={description} onChange={(_e, v) => setDescription(v)} rows={3} aria-label="Job responsibilities" />
      </label>
      <label className="chart-field">
        Instruction prompt
        <TextArea value={prompt} onChange={(_e, v) => setPrompt(v)} rows={5} aria-label="Instruction prompt" />
      </label>
      <label className="chart-field">
        Skills
        <TextInput value={skills} onChange={(_e, v) => setSkills(v)} aria-label="Skills" placeholder="comma-separated skill ids" />
      </label>
      <label className="chart-field">
        Model pool
        <TextInput
          value={models}
          onChange={(_e, v) => setModels(v)}
          aria-label="Preferred models"
          placeholder="provider/model, …"
        />
        <Button size="sm" variant="secondary" onClick={() => setBrowseOpen(true)}>
          Browse models
        </Button>
      </label>
      <ModelBrowseModal
        isOpen={browseOpen}
        onClose={() => setBrowseOpen(false)}
        models={catalog}
        selectedId={split(models)[0] || ''}
        pinnedIds={split(models)}
        onSelect={(id) => {
          const pool = split(models)
          setModels([id, ...pool.filter((m) => m !== id)].join(', '))
          setBrowseOpen(false)
        }}
        onTogglePin={(id) => {
          const pool = split(models)
          setModels((pool.includes(id) ? pool.filter((m) => m !== id) : [...pool, id]).join(', '))
        }}
      />
      <div className="chart-field">
        <span>MCP / tools</span>
        <div className="chart-chips">
          {OPENCODE_TOOL_PERMISSIONS.map((t) => {
            const on = tools.includes(t.id)
            return (
              <button
                key={t.id}
                type="button"
                className={`chart-chip${on ? ' is-on' : ''}`}
                onClick={() =>
                  setTools((prev) => (prev.includes(t.id) ? prev.filter((x) => x !== t.id) : [...prev, t.id]))
                }
              >
                {t.id}
              </button>
            )
          })}
        </div>
        {tools.map((t) => (
          <label key={t} className="chart-perm">
            {t}
            <FormSelect
              value={permission[t] || 'allow'}
              onChange={(_e, v) => setPermission((p) => ({ ...p, [t]: v }))}
              aria-label={`${t} permission`}
            >
              <FormSelectOption value="allow" label="allow" />
              <FormSelectOption value="ask" label="ask" />
              <FormSelectOption value="deny" label="deny" />
            </FormSelect>
          </label>
        ))}
      </div>
      <label className="chart-field">
        Team
        <FormSelect value={teamId} onChange={(_e, v) => setTeamId(v)} aria-label="Team">
          <FormSelectOption value="" label="No team" />
          {teams.map((t) => (
            <FormSelectOption key={t.id} value={t.id} label={`@${t.mention}`} />
          ))}
        </FormSelect>
      </label>
      {seat.kind === 'bot' ? (
        <label className="chart-field">
          Reports to
          <FormSelect value={reportsTo} onChange={(_e, v) => setReportsTo(v)} aria-label="Reports to">
            <FormSelectOption value="" label="(none)" />
            {seats
              .filter((s) => s.id !== seat.id && !s.fired)
              .map((s) => (
                <FormSelectOption key={s.id} value={s.id} label={s.name} />
              ))}
          </FormSelect>
        </label>
      ) : null}

      <Button
        size="sm"
        onClick={() =>
          void onSave({
            description,
            prompt,
            skills: split(skills),
            preferred_models: split(models),
            tools,
            permission,
            team_id: teamId || null,
            reports_to_id: reportsTo || null,
          })
        }
      >
        Save
      </Button>

      <div className="chart-inspector__btns">
        <Button size="sm" variant="secondary" onClick={onOpenRoom}>
          Open room
        </Button>
        {seat.kind === 'bot' ? (
          <>
            <Button size="sm" variant="secondary" onClick={onOpenSession}>
              Open session
            </Button>
            {seat.paused ? (
              <Button size="sm" variant="secondary" onClick={() => void onResume()}>
                Resume
              </Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => void onPause()}>
                Pause
              </Button>
            )}
            <Button size="sm" variant="danger" onClick={() => void onRemove()}>
              Remove
            </Button>
          </>
        ) : null}
      </div>
    </>
  )
}
