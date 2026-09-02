import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  Dropdown,
  DropdownItem,
  DropdownList,
  Label,
  LabelGroup,
  MenuToggle,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Nav,
  NavItem,
  NavList,
  Spinner,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import EllipsisVIcon from '@patternfly/react-icons/dist/esm/icons/ellipsis-v-icon'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import { isDemoMode } from '@/lib/api'
import {
  attachSeat,
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
  const requestTerminalSession = usePlaygroundStore((s) => s.requestTerminalSession)
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
  const [addChannelOpen, setAddChannelOpen] = useState(false)
  const [addTeamOpen, setAddTeamOpen] = useState(false)
  const [newChannel, setNewChannel] = useState('')
  const [newTeam, setNewTeam] = useState('')
  const [channelMenu, setChannelMenu] = useState<string | null>(null)
  const [teamMenu, setTeamMenu] = useState<string | null>(null)
  const [seatMenu, setSeatMenu] = useState<string | null>(null)
  const [participants, setParticipants] = useState<Seat[]>([])

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

  useEffect(() => {
    setParticipants([])
  }, [channelId])

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

  const selectChannel = (id: string) => {
    setChannelId(id)
    if (projectId) void listMessages(projectId, id).then(setMessages)
  }

  const addToChannel = (seat: Seat) => {
    insertMention(seat.slug)
    setParticipants((prev) => (prev.some((p) => p.id === seat.id) ? prev : [...prev, seat]))
  }

  const advancedConversation = async (seat: Seat) => {
    if (!projectId) return
    try {
      if (seat.kind === 'bot') await attachSeat(projectId, seat.id)
      requestTerminalSession({ name: `@${seat.slug}`, cmd: 'opencode' })
      openPanelType('terminal')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Attach seat failed')
    }
  }

  const submitChannel = async () => {
    if (!projectId) return
    const slug = slugify(newChannel)
    if (!slug) return
    try {
      await createChannel(projectId, { name: newChannel, slug })
      setNewChannel('')
      setAddChannelOpen(false)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Add channel failed')
    }
  }

  const submitTeam = async () => {
    if (!projectId) return
    const slug = slugify(newTeam)
    if (!slug) return
    try {
      await createTeam(projectId, { name: newTeam, slug, mention: slug })
      setNewTeam('')
      setAddTeamOpen(false)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Add team failed')
    }
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
        <div className="room-rail__head">
          <div className="room-rail__title">Channels</div>
          <Button
            variant="plain"
            size="sm"
            aria-label="Add channel"
            icon={<PlusIcon />}
            onClick={() => setAddChannelOpen(true)}
          />
        </div>
        <Nav aria-label="Channels" onSelect={(_e, item) => selectChannel(String(item.itemId))}>
          <NavList>
            {channels.map((c) => (
              <NavItem key={c.id} itemId={c.id} isActive={c.id === channelId} preventDefault to={`#${c.slug}`}>
                <span className="room-nav-row">
                  <span>#{c.slug}</span>
                  <span
                    className="room-nav-kebab"
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <Dropdown
                      isOpen={channelMenu === c.id}
                      onOpenChange={(open) => setChannelMenu(open ? c.id : null)}
                      onSelect={() => setChannelMenu(null)}
                      popperProps={{ position: 'right' }}
                      toggle={(toggleRef) => (
                        <MenuToggle
                          ref={toggleRef}
                          variant="plain"
                          aria-label={`#${c.slug} actions`}
                          onClick={() => setChannelMenu((id) => (id === c.id ? null : c.id))}
                          icon={<EllipsisVIcon />}
                        />
                      )}
                    >
                      <DropdownList>
                        <DropdownItem
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
                          Delete
                        </DropdownItem>
                      </DropdownList>
                    </Dropdown>
                  </span>
                </span>
              </NavItem>
            ))}
          </NavList>
        </Nav>

        <div className="room-rail__head">
          <div className="room-rail__title">Teams</div>
          <Button
            variant="plain"
            size="sm"
            aria-label="Add team"
            icon={<PlusIcon />}
            onClick={() => setAddTeamOpen(true)}
          />
        </div>
        <Nav aria-label="Teams">
          <NavList>
            {teams.map((t) => (
              <NavItem
                key={t.id}
                itemId={t.id}
                preventDefault
                to={`#@${t.mention}`}
                onClick={() => insertMention(t.mention)}
              >
                <span className="room-nav-row">
                  <span>@{t.mention}</span>
                  <span
                    className="room-nav-kebab"
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <Dropdown
                      isOpen={teamMenu === t.id}
                      onOpenChange={(open) => setTeamMenu(open ? t.id : null)}
                      onSelect={() => setTeamMenu(null)}
                      popperProps={{ position: 'right' }}
                      toggle={(toggleRef) => (
                        <MenuToggle
                          ref={toggleRef}
                          variant="plain"
                          aria-label={`@${t.mention} actions`}
                          onClick={() => setTeamMenu((id) => (id === t.id ? null : t.id))}
                          icon={<EllipsisVIcon />}
                        />
                      )}
                    >
                      <DropdownList>
                        <DropdownItem
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
                          Delete
                        </DropdownItem>
                      </DropdownList>
                    </Dropdown>
                  </span>
                </span>
              </NavItem>
            ))}
          </NavList>
        </Nav>
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
          {participants.length > 0 ? (
            <LabelGroup className="room-head__people" aria-label="Channel participants" numLabels={6}>
              {participants.map((p) => (
                <Label
                  key={p.id}
                  variant="outline"
                  onClose={() => setParticipants((prev) => prev.filter((x) => x.id !== p.id))}
                >
                  @{p.slug}
                </Label>
              ))}
            </LabelGroup>
          ) : null}
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
          <Dropdown
            key={s.id}
            isOpen={seatMenu === s.id}
            onOpenChange={(open) => setSeatMenu(open ? s.id : null)}
            onSelect={() => setSeatMenu(null)}
            popperProps={{ position: 'left' }}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                className={`room-seat${s.paused ? ' is-paused' : ''}`}
                onClick={() => setSeatMenu((id) => (id === s.id ? null : s.id))}
                aria-label={`${s.name} seat actions`}
              >
                <span className={`room-pip room-pip--${s.status}`} />
                <span>{s.name}</span>
              </MenuToggle>
            )}
          >
            <DropdownList>
              <DropdownItem onClick={() => insertMention(s.slug)}>Mention</DropdownItem>
              <DropdownItem onClick={() => addToChannel(s)}>Add to channel</DropdownItem>
              {s.kind === 'bot' ? (
                <DropdownItem onClick={() => void advancedConversation(s)}>
                  Advanced conversation
                </DropdownItem>
              ) : null}
            </DropdownList>
          </Dropdown>
        ))}
      </aside>

      <Modal
        variant={ModalVariant.small}
        isOpen={addChannelOpen}
        onClose={() => setAddChannelOpen(false)}
        aria-labelledby="add-channel-title"
      >
        <ModalHeader title="Add channel" labelId="add-channel-title" />
        <ModalBody>
          <TextInput
            id="new-channel-name"
            value={newChannel}
            onChange={(_e, v) => setNewChannel(v)}
            placeholder="e.g. ship"
            aria-label="Channel name"
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitChannel()
            }}
          />
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" isDisabled={!slugify(newChannel)} onClick={() => void submitChannel()}>
            Add
          </Button>
          <Button variant="link" onClick={() => setAddChannelOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>

      <Modal
        variant={ModalVariant.small}
        isOpen={addTeamOpen}
        onClose={() => setAddTeamOpen(false)}
        aria-labelledby="add-team-title"
      >
        <ModalHeader title="Add team" labelId="add-team-title" />
        <ModalBody>
          <TextInput
            id="new-team-name"
            value={newTeam}
            onChange={(_e, v) => setNewTeam(v)}
            placeholder="e.g. eng"
            aria-label="Team name"
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitTeam()
            }}
          />
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" isDisabled={!slugify(newTeam)} onClick={() => void submitTeam()}>
            Add
          </Button>
          <Button variant="link" onClick={() => setAddTeamOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
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
