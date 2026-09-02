import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  FormSelect,
  FormSelectOption,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
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

export function ChartPanel({ embedded = false }: { embedded?: boolean }) {
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
    <div className={`chart-layout${embedded ? ' is-embedded' : ''}`}>
      <div className="chart-canvas">
        <header className="chart-head">
          {embedded ? null : <h2>Org chart</h2>}
          <p>Reporting lines. A live run lights the path. Select a bot to configure it.</p>
          <div className="chart-head__row">
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
            <Button size="sm" onClick={() => setAdding(true)}>
              Add seat
            </Button>
            <Checkbox
              id="show-system-seats"
              label="Show system seats"
              isChecked={showSystem}
              onChange={(_e, v) => setShowSystem(v)}
            />
          </div>
          <div className="chart-head__teams">
            {teams.map((t) => (
              <span key={t.id} className="chart-team-chip">
                @{t.mention}
                <button
                  type="button"
                  aria-label={`Remove @${t.mention}`}
                  onClick={() => void act(() => deleteTeam(projectId, t.id))}
                >
                  ×
                </button>
              </span>
            ))}
            <span className="chart-team-add">
              <TextInput
                value={teamName}
                onChange={(_e, v) => setTeamName(v)}
                aria-label="New team name"
                placeholder="New team"
              />
              <Button
                size="sm"
                variant="secondary"
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
            </span>
          </div>
        </header>
        {error ? <div className="room-error">{error}</div> : null}

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
          <p className="chart-inspector__empty">Select a seat.</p>
        )}
      </aside>

      <Modal
        variant={ModalVariant.small}
        isOpen={adding}
        onClose={() => setAdding(false)}
        aria-label="Add seat"
      >
        <ModalHeader title="Add seat" />
        <ModalBody>
          <div className="chart-add-form">
            <label>
              Name
              <TextInput value={addName} onChange={(_e, v) => setAddName(v)} aria-label="New seat name" />
            </label>
            <label>
              Template
              <FormSelect value={addTemplate} onChange={(_e, v) => setAddTemplate(v)} aria-label="Template">
                {['scout', 'docs', 'sec', 'scribe', 'product', 'qa'].map((t) => (
                  <FormSelectOption key={t} value={t} label={t} />
                ))}
              </FormSelect>
            </label>
            <label>
              Team
              <FormSelect value={addTeamId} onChange={(_e, v) => setAddTeamId(v)} aria-label="Team">
                <FormSelectOption value="" label="No team" />
                {teams.map((t) => (
                  <FormSelectOption key={t.id} value={t.id} label={`@${t.mention}`} />
                ))}
              </FormSelect>
            </label>
            <label>
              Reports to
              <FormSelect value={addReportsTo} onChange={(_e, v) => setAddReportsTo(v)} aria-label="Reports to">
                <FormSelectOption value="" label="None" />
                {visibleSeats.map((s) => (
                  <FormSelectOption key={s.id} value={s.id} label={s.name} />
                ))}
              </FormSelect>
            </label>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button
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
          <Button variant="link" onClick={() => setAdding(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
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
      <div className={`org-node${kids.length > 0 ? ' is-parent' : ''}`}>
        <SeatCard
          seat={seat}
          team={team}
          lit={pathSlugs.has(seat.slug)}
          selected={seat.id === selectedId}
          onSelect={() => onSelect(seat.id)}
        />
      </div>
      {kids.length > 0 ? (
        <div className="org-kids" role="group">
          {kids.map((child) => (
            <div key={child.id} className="org-kid">
              <OrgBranch
                seat={child}
                childrenOf={childrenOf}
                teams={teams}
                pathSlugs={pathSlugs}
                selectedId={selectedId}
                onSelect={onSelect}
              />
            </div>
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
      className={`seat-card${seat.kind === 'human' ? ' is-human' : ''}${lit ? ' is-lit' : ''}${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
    >
      <span className="seat-card__name">{seat.name}</span>
      <span className="seat-card__role">{seat.role}</span>
      {team ? <span className="seat-card__team">@{team.mention}</span> : null}
    </button>
  )
}

const PERMS = ['allow', 'ask', 'deny'] as const

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

  const reportsName = byId[seat.reports_to_id || '']?.name

  return (
    <>
      <h3>{seat.name}</h3>
      <p className="chart-inspector__meta">
        {seat.kind}
        {seat.paused ? ', paused' : ''}
        {reportsName ? `, reports to ${reportsName}` : ''}
      </p>

      <section className="chart-group">
        <h4>Job</h4>
        <label className="chart-field">
          Responsibilities
          <TextArea
            value={description}
            onChange={(_e, v) => setDescription(v)}
            rows={3}
            aria-label="Job responsibilities"
          />
        </label>
      </section>

      <section className="chart-group">
        <h4>Instructions</h4>
        <label className="chart-field">
          Prompt
          <TextArea value={prompt} onChange={(_e, v) => setPrompt(v)} rows={5} aria-label="Instruction prompt" />
        </label>
      </section>

      <section className="chart-group">
        <h4>Skills and models</h4>
        <label className="chart-field">
          Skills
          <TextInput
            value={skills}
            onChange={(_e, v) => setSkills(v)}
            aria-label="Skills"
            placeholder="skill ids"
          />
        </label>
        <label className="chart-field">
          Model pool
          <TextInput
            value={models}
            onChange={(_e, v) => setModels(v)}
            aria-label="Preferred models"
            placeholder="provider/model"
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
      </section>

      <section className="chart-group">
        <h4>Tools</h4>
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
          <div key={t} className="chart-perm">
            <span>{t}</span>
            <div className="chart-seg" role="group" aria-label={`${t} permission`}>
              {PERMS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={(permission[t] || 'allow') === p ? 'is-on' : ''}
                  onClick={() => setPermission((prev) => ({ ...prev, [t]: p }))}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="chart-group">
        <h4>Placement</h4>
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
              <FormSelectOption value="" label="None" />
              {seats
                .filter((s) => s.id !== seat.id && !s.fired)
                .map((s) => (
                  <FormSelectOption key={s.id} value={s.id} label={s.name} />
                ))}
            </FormSelect>
          </label>
        ) : null}
      </section>

      <Button
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
          </>
        ) : null}
      </div>
      {seat.kind === 'bot' ? (
        <div className="chart-inspector__remove">
          <Button size="sm" variant="danger" onClick={() => void onRemove()}>
            Remove
          </Button>
        </div>
      ) : null}
    </>
  )
}
