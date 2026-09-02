import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Checkbox, Spinner, TextArea, TextInput } from '@patternfly/react-core'
import { isDemoMode } from '@/lib/api'
import {
  createChannel,
  createTeam,
  deleteChannel,
  deleteTeam,
  getRun,
  listChannels,
  listMessages,
  listSeats,
  listTeams,
  postMessage,
} from '@/lib/orgApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { Channel, ChannelMessage, OrgRun, Seat, Team } from '@/types/org'

const DEMO_SENTENCE =
  'Talk to Product and the Eng team. When they complete, have DevOps deploy to staging and QA test everything.'

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function RoomPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const [channels, setChannels] = useState<Channel[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [channelId, setChannelId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChannelMessage[]>([])
  const [seats, setSeats] = useState<Seat[]>([])
  const [run, setRun] = useState<OrgRun | null>(null)
  const [draft, setDraft] = useState(DEMO_SENTENCE)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSystem, setShowSystem] = useState(false)
  const [newChannel, setNewChannel] = useState('')
  const [newTeam, setNewTeam] = useState('')

  const seatById = useMemo(() => Object.fromEntries(seats.map((s) => [s.id, s])), [seats])
  const active = channels.find((c) => c.id === channelId)

  const refresh = useCallback(async () => {
    if (!projectId || isDemoMode()) {
      setLoading(false)
      return
    }
    setError(null)
    try {
      const [ch, st, tm] = await Promise.all([
        listChannels(projectId),
        listSeats(projectId, { includeSystem: showSystem }),
        listTeams(projectId),
      ])
      setChannels(ch)
      setSeats(st.filter((s) => !s.fired))
      setTeams(tm)
      const ship = ch.find((c) => c.slug === 'ship') || ch[0]
      const cid = ship?.id || null
      setChannelId((prev) => (prev && ch.some((c) => c.id === prev) ? prev : cid))
      const useId = channelId && ch.some((c) => c.id === channelId) ? channelId : cid
      if (useId) {
        const msgs = await listMessages(projectId, useId)
        setMessages(msgs)
        const lastRun = [...msgs].reverse().find((m) => m.run_id)
        if (lastRun?.run_id) setRun(await getRun(projectId, lastRun.run_id))
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load room')
    } finally {
      setLoading(false)
    }
  }, [projectId, showSystem, channelId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const send = async () => {
    if (!projectId || !channelId || !draft.trim()) return
    setSending(true)
    try {
      const msg = await postMessage(projectId, channelId, draft.trim())
      setDraft('')
      const msgs = await listMessages(projectId, channelId)
      setMessages(msgs)
      if (msg.run_id) setRun(await getRun(projectId, msg.run_id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Send failed')
    } finally {
      setSending(false)
    }
  }

  const insertMention = (handle: string) => {
    setDraft((d) => (d.trim() ? `${d.replace(/\s+$/, '')} @${handle} ` : `@${handle} `))
  }

  if (!projectId) {
    return <div className="room-empty">Open a project to use the room.</div>
  }
  if (isDemoMode()) {
    return <div className="room-empty">Room needs a live project. Create or open a project.</div>
  }
  if (loading) {
    return (
      <div className="room-empty">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="room-layout">
      <aside className="room-rail" aria-label="Channels">
        <div className="room-rail__title">Channels</div>
        {channels.map((c) => (
          <div key={c.id} className="room-ch-row">
            <button
              type="button"
              className={`room-ch${c.id === channelId ? ' is-active' : ''}`}
              onClick={() => {
                setChannelId(c.id)
                void listMessages(projectId, c.id).then(setMessages)
              }}
            >
              #{c.slug}
            </button>
            <Button
              size="sm"
              variant="plain"
              aria-label={`Remove #${c.slug}`}
              onClick={() =>
                void (async () => {
                  try {
                    await deleteChannel(projectId, c.id)
                    await refresh()
                  } catch (e) {
                    setError(e instanceof Error ? e.message : 'Remove channel failed')
                  }
                })()
              }
            >
              ×
            </Button>
          </div>
        ))}
        <div className="room-rail__add">
          <TextInput
            value={newChannel}
            onChange={(_e, v) => setNewChannel(v)}
            aria-label="New channel name"
            placeholder="New channel"
          />
          <Button
            size="sm"
            onClick={() =>
              void (async () => {
                const slug = slugify(newChannel)
                if (!slug) return
                try {
                  await createChannel(projectId, { name: newChannel, slug })
                  setNewChannel('')
                  await refresh()
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Add channel failed')
                }
              })()
            }
          >
            Add
          </Button>
        </div>

        <div className="room-rail__title">Teams</div>
        <div className="room-mentions">
          {teams.map((t) => (
            <span key={t.id} className="chart-team-chip">
              <button type="button" className="chart-chip" onClick={() => insertMention(t.mention)}>
                @{t.mention}
              </button>
              <button
                type="button"
                aria-label={`Remove @${t.mention}`}
                onClick={() =>
                  void (async () => {
                    try {
                      await deleteTeam(projectId, t.id)
                      await refresh()
                    } catch (e) {
                      setError(e instanceof Error ? e.message : 'Remove team failed')
                    }
                  })()
                }
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="room-rail__add">
          <TextInput
            value={newTeam}
            onChange={(_e, v) => setNewTeam(v)}
            aria-label="New team name"
            placeholder="New team"
          />
          <Button
            size="sm"
            onClick={() =>
              void (async () => {
                const slug = slugify(newTeam)
                if (!slug) return
                try {
                  await createTeam(projectId, { name: newTeam, slug, mention: slug })
                  setNewTeam('')
                  await refresh()
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Add team failed')
                }
              })()
            }
          >
            Add
          </Button>
        </div>
        <Checkbox
          id="room-show-system"
          label="Show system seats"
          isChecked={showSystem}
          onChange={(_e, v) => setShowSystem(v)}
        />
      </aside>

      <section className="room-main">
        <header className="room-head">
          <h2>#{active?.slug || 'ship'}</h2>
          <span className="room-head__meta">Thread is the audit log</span>
        </header>
        {error ? <div className="room-error">{error}</div> : null}
        {run ? <RunCard run={run} /> : null}
        <div className="room-msgs">
          {messages.length === 0 ? (
            <p className="room-hint">Speak in the channel. Bots pick up the work and hand it along.</p>
          ) : (
            messages.map((m) => (
              <article key={m.id} className={`room-msg room-msg--${m.kind}`}>
                <div className="room-msg__who">
                  {m.author_seat_id
                    ? seatById[m.author_seat_id]?.name || 'Seat'
                    : m.kind === 'run_event'
                      ? 'System'
                      : 'You'}
                </div>
                <div className="room-msg__body">{m.body}</div>
              </article>
            ))
          )}
        </div>
        <div className="room-composer">
          <div className="room-mentions">
            {teams.map((t) => (
              <button key={t.id} type="button" className="chart-chip" onClick={() => insertMention(t.mention)}>
                @{t.mention}
              </button>
            ))}
            {seats
              .filter((s) => s.kind === 'bot')
              .map((s) => (
                <button key={s.id} type="button" className="chart-chip" onClick={() => insertMention(s.slug)}>
                  @{s.slug}
                </button>
              ))}
          </div>
          <div className="room-composer__row">
            <TextArea value={draft} onChange={(_e, v) => setDraft(v)} aria-label="Message" rows={3} />
            <Button variant="primary" onClick={() => void send()} isDisabled={sending || !draft.trim()}>
              Send
            </Button>
          </div>
        </div>
      </section>

      <aside className="room-roster" aria-label="Roster">
        <div className="room-rail__title">Seats</div>
        {seats.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`room-seat${s.paused ? ' is-paused' : ''}`}
            onClick={() => {
              if (s.kind === 'bot') openPanelType('terminal')
            }}
            title={s.description}
          >
            <span className={`room-pip room-pip--${s.status}`} />
            <span>{s.name}</span>
          </button>
        ))}
      </aside>
    </div>
  )
}

function RunCard({ run }: { run: OrgRun }) {
  return (
    <div className="run-card" aria-label="Run card">
      <div className="run-card__title">
        {run.title.slice(0, 48)} ({run.status})
      </div>
      <ol className="run-card__steps">
        {run.nodes.map((n) => (
          <li key={n.id} className={`run-step run-step--${n.status}`}>
            <span className="run-step__label">{n.label}</span>
            <span className="run-step__st">{n.status}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
