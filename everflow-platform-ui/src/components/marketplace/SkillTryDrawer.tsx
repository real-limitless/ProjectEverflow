import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  FormSelect,
  FormSelectOption,
  Label,
  Spinner,
  TextArea,
} from '@patternfly/react-core'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'
import type { MarketplaceItem } from '@/data/marketplace'
import {
  getMarketplaceInstalled,
  installMarketplaceItem,
  isDemoMode,
  listProjects,
  uninstallMarketplaceItem,
  type ApiProject,
} from '@/lib/api'
import {
  canUseOpenCode,
  createSession,
  deleteSession,
  ensureOpenCode,
  listMessages,
  promptAsync,
  promptSync,
} from '@/lib/opencode/client'
import { openCodePromptForMode } from '@/lib/opencode/chatMode'
import { mapOcMessages, messageHasReplyText } from '@/lib/opencode/mapParts'
import { markdownToHtml } from '@/lib/chatMarkdown'
import { pushToast } from '@/lib/studioToast'
import { useAuthStore } from '@/store/authStore'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { getProject } from '@/data/projects'

type TryPhase = 'idle' | 'loading' | 'ready' | 'sending' | 'error'

type TryMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  streaming?: boolean
}

const SUGGESTIONS = [
  'What does this skill do?',
  'Walk me through a live example on this project.',
  'What tools and files will you use?',
]

interface SkillTryDrawerProps {
  item: MarketplaceItem
  open: boolean
  onClose: () => void
}

export function SkillTryDrawer({ item, open, onClose }: SkillTryDrawerProps) {
  const org = useAuthStore((s) => s.org)
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)

  const [projects, setProjects] = useState<ApiProject[]>([])
  const [projectId, setProjectId] = useState('')
  const [phase, setPhase] = useState<TryPhase>('idle')
  const [statusText, setStatusText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<TryMessage[]>([])
  const [draft, setDraft] = useState('')
  const [keepInstalled, setKeepInstalled] = useState(false)
  const [installedForTry, setInstalledForTry] = useState(false)
  const [sessionActive, setSessionActive] = useState(false)

  const sessionIdRef = useRef<string | null>(null)
  const installedForTryRef = useRef(false)
  const keepInstalledRef = useRef(false)
  const pollRef = useRef<number | null>(null)
  const closedRef = useRef(false)
  const listEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    keepInstalledRef.current = keepInstalled
  }, [keepInstalled])

  const stopPoll = () => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const cleanup = useCallback(async () => {
    stopPoll()
    const sid = sessionIdRef.current
    const pid = projectId
    sessionIdRef.current = null
    if (pid && sid) {
      try {
        await deleteSession(pid, sid)
      } catch {
        /* best-effort */
      }
    }
    if (pid && installedForTryRef.current && !keepInstalledRef.current) {
      try {
        await uninstallMarketplaceItem(pid, item.kind, item.id)
        window.dispatchEvent(
          new CustomEvent('everflow:harness-updated', { detail: { projectId: pid } }),
        )
      } catch {
        /* best-effort */
      }
    }
    installedForTryRef.current = false
    setInstalledForTry(false)
    setSessionActive(false)
  }, [item.id, item.kind, projectId])

  const handleClose = useCallback(async () => {
    closedRef.current = true
    setPhase('idle')
    await cleanup()
    onClose()
  }, [cleanup, onClose])

  // Load projects when drawer opens
  useEffect(() => {
    if (!open) return
    closedRef.current = false
    setError(null)
    setMessages([])
    setDraft('')
    setKeepInstalled(false)
    setInstalledForTry(false)
    setSessionActive(false)
    setPhase('loading')
    setStatusText('Loading projects…')

    if (demoMode || !org?.id) {
      setProjects([])
      setPhase('idle')
      setStatusText('')
      return
    }

    let cancelled = false
    void (async () => {
      try {
        const rows = await listProjects(org.id)
        if (cancelled) return
        setProjects(rows)
        const running = rows.filter((p) => p.sandbox_status === 'running')
        const preferred =
          running.find((p) => p.id === currentProjectId)?.id ||
          running[0]?.id ||
          ''
        setProjectId(preferred)
        setPhase(preferred ? 'idle' : 'idle')
        setStatusText(preferred ? '' : 'Pick a project with a running sandbox.')
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load projects')
          setPhase('error')
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [open, demoMode, org?.id, currentProjectId])

  // Cleanup on unmount if a try session is still live
  useEffect(() => {
    return () => {
      stopPoll()
      if (sessionIdRef.current && projectId) {
        const sid = sessionIdRef.current
        const pid = projectId
        const shouldUninstall = installedForTryRef.current && !keepInstalledRef.current
        sessionIdRef.current = null
        void deleteSession(pid, sid).catch(() => undefined)
        if (shouldUninstall) {
          void uninstallMarketplaceItem(pid, item.kind, item.id).catch(() => undefined)
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
  }, [])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, phase])

  const attachAndStart = async () => {
    if (!projectId || demoMode) return
    setError(null)
    setPhase('loading')
    setStatusText('Preparing harness…')
    installedForTryRef.current = false
    setInstalledForTry(false)

    try {
      const catalogProject = getProject(projectId)
      const apiRow = projects.find((p) => p.id === projectId)
      const sandboxOk =
        apiRow?.sandbox_status === 'running' ||
        canUseOpenCode({
          fromApi: catalogProject?.fromApi ?? true,
          sandboxStatus: catalogProject?.sandboxStatus || apiRow?.sandbox_status || '',
        })
      if (!sandboxOk) {
        throw new Error('Sandbox must be running to try this skill')
      }

      // Already installed?
      let already = false
      try {
        const inst = await getMarketplaceInstalled(projectId)
        already = (inst.items || []).some(
          (i) => i.kind === item.kind && i.id === item.id,
        )
      } catch {
        already = false
      }

      if (!already) {
        setStatusText(`Installing “${item.name}” into harness…`)
        await installMarketplaceItem(projectId, item.kind, item.id)
        installedForTryRef.current = true
        setInstalledForTry(true)
        window.dispatchEvent(
          new CustomEvent('everflow:harness-updated', { detail: { projectId } }),
        )
      }

      setStatusText('Starting OpenCode…')
      await ensureOpenCode(projectId)

      setStatusText('Creating try session…')
      const session = await createSession(projectId, `Try: ${item.name}`)
      if (closedRef.current) {
        await deleteSession(projectId, session.id).catch(() => undefined)
        return
      }
      sessionIdRef.current = session.id
      setSessionActive(true)

      const tempNote = installedForTryRef.current
        ? ' and remove the temporary install (unless you keep it).'
        : '.'
      setMessages([
        {
          id: 'sys-welcome',
          role: 'system',
          text: `Live try of **${item.name}** on this project harness. Mode defaults to Ask (read-only tools). Close the drawer to end the session${tempNote}`,
        },
      ])
      setPhase('ready')
      setStatusText('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start try session')
      setPhase('error')
      setStatusText('')
      setSessionActive(false)
      await cleanup()
    }
  }

  const pollMessages = (pid: string, sid: string) => {
    stopPoll()
    pollRef.current = window.setInterval(() => {
      void (async () => {
        try {
          const list = await listMessages(pid, sid)
          const mapped = mapOcMessages(list)
          const ui: TryMessage[] = mapped
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({
              id: m.id,
              role: m.role as 'user' | 'assistant',
              text:
                m.text ||
                m.blocks?.map((b) => b.text || '').join('\n') ||
                (m.generationStatus === 'incomplete' ? '…' : ''),
              streaming: m.generationStatus === 'incomplete',
            }))
          setMessages((prev) => {
            const sys = prev.filter((m) => m.role === 'system')
            return [...sys, ...ui]
          })
          const lastAsst = [...mapped].reverse().find((m) => m.role === 'assistant')
          if (lastAsst && messageHasReplyText(lastAsst) && lastAsst.generationStatus !== 'incomplete') {
            stopPoll()
            setPhase('ready')
          }
        } catch {
          /* keep polling */
        }
      })()
    }, 700)
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    const sid = sessionIdRef.current
    if (!trimmed || !sid || !projectId || phase === 'sending') return

    setDraft('')
    setPhase('sending')
    setError(null)

    const userLocal: TryMessage = {
      id: `local-u-${Date.now()}`,
      role: 'user',
      text: trimmed,
    }
    setMessages((prev) => [
      ...prev,
      userLocal,
      { id: `local-a-${Date.now()}`, role: 'assistant', text: '…', streaming: true },
    ])

    const modePrompt = openCodePromptForMode('ask')
    const system = [
      `You are demonstrating the marketplace ${item.kind} “${item.name}” (id: ${item.id}).`,
      `The skill/command is installed on this project's OpenCode harness for a live try session.`,
      `Explain how it works, prefer invoking or following its guidance, and keep answers grounded in this project.`,
      `Stay in read-only mode unless the user explicitly asks to change files.`,
      item.description ? `Catalog blurb: ${item.description}` : '',
    ]
      .filter(Boolean)
      .join('\n')

    const body = {
      parts: [{ type: 'text', text: trimmed }],
      agent: 'build',
      system,
      tools: modePrompt.tools,
    }

    try {
      try {
        await promptAsync(projectId, sid, body)
      } catch {
        await promptSync(projectId, sid, body)
      }
      pollMessages(projectId, sid)
      // Safety timeout so UI doesn't stick in sending forever
      window.setTimeout(() => {
        if (!closedRef.current) setPhase((p) => (p === 'sending' ? 'ready' : p))
      }, 90_000)
    } catch (e) {
      stopPoll()
      setError(e instanceof Error ? e.message : 'Send failed')
      setPhase('error')
      pushToast(e instanceof Error ? e.message : 'Send failed', { kind: 'danger' })
    }
  }

  if (!open) return null

  const runningProjects = projects.filter((p) => p.sandbox_status === 'running')
  const inSession = sessionActive && (phase === 'ready' || phase === 'sending' || phase === 'error')

  return (
    <>
      <button
        type="button"
        className="mp-try-backdrop"
        aria-label="Close try chat"
        onClick={() => void handleClose()}
      />
      <div className="mp-try-drawer" role="dialog" aria-modal="true" aria-label={`Try ${item.name}`}>
      <div className="mp-try-drawer__header">
        <div>
          <h2 className="mp-try-drawer__title">Try “{item.name}”</h2>
          <p className="mp-try-drawer__sub">
            Ephemeral chat · harness-backed · Ask mode
          </p>
        </div>
        <Button variant="plain" aria-label="Close try chat" onClick={() => void handleClose()} icon={<TimesIcon />} />
      </div>

      <div className="mp-try-drawer__body">
        {demoMode || !org?.id ? (
          <div className="mp-try-empty">
            <p>Sign in and open a project with a running sandbox to live-test skills.</p>
            <Button
              variant="primary"
              onClick={() => {
                void handleClose()
                setOpenProjectModal(true)
              }}
            >
              Open a project
            </Button>
          </div>
        ) : !inSession ? (
          <div className="mp-try-setup">
            <label className="mp-try-label" htmlFor="mp-try-project">
              Project harness
            </label>
            <FormSelect
              id="mp-try-project"
              value={projectId}
              onChange={(_e, v) => setProjectId(v)}
              aria-label="Select project"
              isDisabled={phase === 'loading' || !runningProjects.length}
            >
              {!runningProjects.length ? (
                <FormSelectOption value="" label="No running sandboxes" />
              ) : (
                runningProjects.map((p) => (
                  <FormSelectOption key={p.id} value={p.id} label={`${p.name} (${p.sandbox_status})`} />
                ))
              )}
            </FormSelect>
            <p className="mp-try-hint">
              We temporarily install the skill on the selected project if needed, open an OpenCode
              session, and clean up when you close.
            </p>
            {phase === 'loading' ? (
              <div className="mp-try-status">
                <Spinner size="md" /> <span>{statusText || 'Working…'}</span>
              </div>
            ) : null}
            {error ? <p className="mp-try-error">{error}</p> : null}
            <Button
              variant="primary"
              onClick={() => void attachAndStart()}
              isDisabled={!projectId || phase === 'loading' || !runningProjects.length}
            >
              Start live try
            </Button>
          </div>
        ) : (
          <>
            <div className="mp-try-banner">
              <Label color="green" isCompact>
                Live
              </Label>
              <span>
                {projects.find((p) => p.id === projectId)?.name || projectId}
                {installedForTry ? ' · temp install' : ' · already installed'}
              </span>
              {installedForTry ? (
                <label className="mp-try-keep">
                  <input
                    type="checkbox"
                    checked={keepInstalled}
                    onChange={(e) => setKeepInstalled(e.target.checked)}
                  />{' '}
                  Keep installed
                </label>
              ) : null}
            </div>
            <div className="mp-try-messages">
              {messages.map((m) => (
                <div key={m.id} className={`mp-try-msg mp-try-msg--${m.role}`}>
                  <div
                    className="mp-try-msg__bubble"
                    dangerouslySetInnerHTML={{
                      __html: markdownToHtml(m.text || (m.streaming ? '…' : '')),
                    }}
                  />
                </div>
              ))}
              <div ref={listEndRef} />
            </div>
            {phase === 'ready' && messages.filter((m) => m.role === 'user').length === 0 ? (
              <div className="mp-try-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="mp-try-chip" onClick={() => void send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            ) : null}
            {error ? <p className="mp-try-error">{error}</p> : null}
            <div className="mp-try-composer">
              <TextArea
                value={draft}
                onChange={(_e, v) => setDraft(v)}
                aria-label="Try chat message"
                rows={2}
                placeholder="Ask how this skill works…"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send(draft)
                  }
                }}
                isDisabled={phase === 'sending'}
              />
              <Button
                variant="primary"
                onClick={() => void send(draft)}
                isDisabled={!draft.trim() || phase === 'sending'}
                isLoading={phase === 'sending'}
              >
                Send
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
    </>
  )
}
