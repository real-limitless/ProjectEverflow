import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Spinner, TextArea } from '@patternfly/react-core'
import { isDemoMode } from '@/lib/api'
import {
  getRun,
  listChannels,
  listMessages,
  listSeats,
  postMessage,
} from '@/lib/orgApi'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { Channel, ChannelMessage, OrgRun, Seat } from '@/types/org'

const DEMO_SENTENCE =
  'Talk to Product and the Eng team. When they complete, have DevOps deploy to staging and QA test everything.'

export function RoomPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const setSurfaceMode = usePlaygroundStore((s) => s.setSurfaceMode)
  const [channels, setChannels] = useState<Channel[]>([])
  const [channelId, setChannelId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChannelMessage[]>([])
  const [seats, setSeats] = useState<Seat[]>([])
  const [run, setRun] = useState<OrgRun | null>(null)
  const [draft, setDraft] = useState(DEMO_SENTENCE)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const seatById = useMemo(() => Object.fromEntries(seats.map((s) => [s.id, s])), [seats])
  const active = channels.find((c) => c.id === channelId)

  const refresh = useCallback(async () => {
    if (!projectId || isDemoMode()) {
      setLoading(false)
      return
    }
    setError(null)
    try {
      const [ch, st] = await Promise.all([listChannels(projectId), listSeats(projectId)])
      setChannels(ch)
      setSeats(st.filter((s) => !s.fired))
      const ship = ch.find((c) => c.slug === 'ship') || ch[0]
      const cid = ship?.id || null
      setChannelId((prev) => prev || cid)
      const useId = cid
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
  }, [projectId])

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

  if (!projectId) {
    return <div className="room-empty">Open a project to use the room.</div>
  }
  if (isDemoMode()) {
    return (
      <div className="room-empty">
        Room needs a live project. Create or open a project (not demo mode).
      </div>
    )
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
          <button
            key={c.id}
            type="button"
            className={`room-ch${c.id === channelId ? ' is-active' : ''}`}
            onClick={() => {
              setChannelId(c.id)
              void listMessages(projectId, c.id).then(setMessages)
            }}
          >
            #{c.slug}
          </button>
        ))}
        <div className="room-rail__title" style={{ marginTop: 16 }}>
          Teams
        </div>
        {['eng', 'services'].map((m) => (
          <div key={m} className="room-ch room-ch--static">
            @{m}
          </div>
        ))}
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
            <p className="room-hint">
              Speak in #ship. Floor compiles a run. Each node is a seat you can open in Harness.
            </p>
          ) : (
            messages.map((m) => (
              <article key={m.id} className={`room-msg room-msg--${m.kind}`}>
                <div className="room-msg__who">
                  {m.author_seat_id
                    ? seatById[m.author_seat_id]?.name || 'Seat'
                    : m.kind === 'run_event'
                      ? 'Floor'
                      : 'You'}
                </div>
                <div className="room-msg__body">{m.body}</div>
              </article>
            ))
          )}
        </div>
        <div className="room-composer">
          <TextArea
            value={draft}
            onChange={(_e, v) => setDraft(v)}
            aria-label="Message #ship"
            rows={3}
          />
          <Button variant="primary" onClick={() => void send()} isDisabled={sending || !draft.trim()}>
            Send
          </Button>
        </div>
      </section>

      <aside className="room-roster" aria-label="Roster">
        <div className="room-rail__title">Seats</div>
        {seats.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`room-seat${s.kind === 'bot' ? ' is-bot' : ''}${s.paused ? ' is-paused' : ''}`}
            onClick={() => {
              if (s.kind === 'bot') setSurfaceMode('harness')
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
        Pipeline · {run.title.slice(0, 48)} · {run.status}
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
