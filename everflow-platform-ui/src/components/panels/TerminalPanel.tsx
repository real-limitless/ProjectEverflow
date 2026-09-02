import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Spinner } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import {
  ApiError,
  getSandboxStatus,
  recreateSandbox,
} from '@/lib/api'
import { waitForSandbox } from '@/lib/sandboxPoll'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import {
  InteractiveSandboxTerminal,
  type InteractiveTerminalHandle,
} from './InteractiveSandboxTerminal'
import { SandboxXterm, type SandboxXtermHandle } from './SandboxXterm'

type SessionMeta = {
  id: string
  name: string
  /** If set, WS launches this command instead of an interactive shell. */
  cmd?: string
}

function newSessionMeta(index: number, cmd?: string): SessionMeta {
  return {
    id: `sh-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 5)}`,
    name: cmd ? cmd.split(/\s+/)[0] || `shell-${index + 1}` : index === 0 ? 'shell' : `shell-${index + 1}`,
    cmd,
  }
}

/**
 * Terminal panel:
 * - API projects → interactive PTY WebSocket (opencode, bash, etc.)
 * - Local demo projects → line-mode xterm (no remote)
 */
export function TerminalPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const prefill = usePlaygroundStore((s) => s.terminalPrefill)
  const clearTerminalPrefill = usePlaygroundStore((s) => s.clearTerminalPrefill)
  const sessionRequest = usePlaygroundStore((s) => s.terminalSessionRequest)
  const clearTerminalSessionRequest = usePlaygroundStore((s) => s.clearTerminalSessionRequest)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const p = getProject(currentProjectId)
  void catalogVersion

  const [sessions, setSessions] = useState<SessionMeta[]>(() => [newSessionMeta(0)])
  const [activeId, setActiveId] = useState(() => sessions[0]?.id ?? '')
  const [recreating, setRecreating] = useState(false)
  const [, setWsStatus] = useState<string>('')
  const handlesRef = useRef<Record<string, InteractiveTerminalHandle | SandboxXtermHandle | null>>(
    {},
  )
  // Remount key when sandbox recreated so WS reconnects cleanly
  const [sessionEpoch, setSessionEpoch] = useState(0)

  useEffect(() => {
    const first = newSessionMeta(0)
    setSessions([first])
    setActiveId(first.id)
    handlesRef.current = {}
    setSessionEpoch((e) => e + 1)
  }, [currentProjectId])

  const active = sessions.find((s) => s.id === activeId) ?? sessions[0]
  const status = p?.sandboxStatus || 'unknown'
  // UUID project ids from the API must use interactive PTY (not line-mode demo).
  const looksLikeApiId =
    Boolean(currentProjectId) &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      currentProjectId || '',
    )
  const isApiProject = Boolean(p?.fromApi) || looksLikeApiId
  const sandboxReady = Boolean(isApiProject && status === 'running')
  const needsRecreate =
    isApiProject &&
    (status === 'error' ||
      status === 'destroyed' ||
      (status !== 'running' &&
        status !== 'pending' &&
        status !== 'creating' &&
        status !== 'stopped' &&
        status !== 'unknown'))
  const provisioning = status === 'pending' || status === 'creating'
  const syncStatus = useCallback(async () => {
    if (!p?.fromApi || !currentProjectId) return
    try {
      const st = await getSandboxStatus(currentProjectId)
      patchProjectSandbox(currentProjectId, {
        sandboxStatus: st.status,
        sandboxName: st.sandbox_name,
        sandboxError: st.error,
        sandboxImage: st.image,
        sandboxCreatedAt: st.created_at,
      })
    } catch {
      /* ignore */
    }
  }, [p?.fromApi, currentProjectId, patchProjectSandbox])

  useEffect(() => {
    if (!p?.fromApi || !currentProjectId) return
    void syncStatus()
    const id = window.setInterval(() => void syncStatus(), 5000)
    return () => window.clearInterval(id)
  }, [p?.fromApi, currentProjectId, syncStatus])

  // Agents panel: send command into interactive shell (or open dedicated session)
  useEffect(() => {
    if (!prefill || !active) return
    const h = handlesRef.current[active.id]
    if (h && 'sendLine' in h && typeof h.sendLine === 'function') {
      h.sendLine(prefill)
      h.focus()
    } else if (h && 'setLine' in h) {
      ;(h as SandboxXtermHandle).setLine(prefill)
      h.focus()
    }
    clearTerminalPrefill()
  }, [prefill, active, clearTerminalPrefill])

  useEffect(() => {
    if (!sessionRequest) return
    setSessions((prev) => {
      const existing = prev.find((s) => s.name === sessionRequest.name)
      if (existing) {
        setActiveId(existing.id)
        return prev
      }
      const next: SessionMeta = {
        id: `sh-${Date.now()}-adv-${Math.random().toString(36).slice(2, 5)}`,
        name: sessionRequest.name,
        cmd: sessionRequest.cmd,
      }
      setActiveId(next.id)
      return [...prev, next]
    })
    clearTerminalSessionRequest()
  }, [sessionRequest, clearTerminalSessionRequest])

  const doRecreate = async () => {
    if (!p?.fromApi || !currentProjectId || recreating) return
    setRecreating(true)
    try {
      await recreateSandbox(currentProjectId)
      patchProjectSandbox(currentProjectId, {
        sandboxStatus: 'creating',
        sandboxError: null,
      })
      const st = await waitForSandbox(currentProjectId, {
        onUpdate: (s) => {
          patchProjectSandbox(currentProjectId, {
            sandboxStatus: s.status,
            sandboxName: s.sandbox_name,
            sandboxError: s.error,
            sandboxImage: s.image,
            sandboxCreatedAt: s.created_at,
          })
        },
      })
      if (st.status === 'running') {
        pushToast('Sandbox recreated', { kind: 'success' })
        setSessionEpoch((e) => e + 1)
      } else {
        pushToast(st.error || 'Sandbox recreate failed', { kind: 'danger' })
      }
    } catch (e) {
      pushToast(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'recreate failed', {
        kind: 'danger',
      })
    } finally {
      setRecreating(false)
    }
  }

  const addSession = (cmd?: string) => {
    const s = newSessionMeta(sessions.length, cmd)
    setSessions((prev) => [...prev, s])
    setActiveId(s.id)
  }

  const closeSession = (id: string) => {
    setSessions((prev) => {
      if (prev.length <= 1) return prev
      const next = prev.filter((s) => s.id !== id)
      if (activeId === id) setActiveId(next[0]?.id ?? '')
      delete handlesRef.current[id]
      return next
    })
  }

  const clearActive = () => {
    if (!active) return
    handlesRef.current[active.id]?.clear()
  }

  const useInteractive = Boolean(isApiProject && currentProjectId)
  const inputEnabled = !recreating && (isApiProject ? sandboxReady : true)

  return (
    <div className="term-wrap term-wrap--xterm">
      <div className="term-toolbar">
        <span>{active?.name || 'Shell'}</span>
        <Button variant="link" size="sm" onClick={clearActive}>
          Clear
        </Button>
        <Button variant="link" size="sm" onClick={() => addSession()} aria-label="New shell">
          New
        </Button>
        {useInteractive && sandboxReady ? (
          <Button
            variant="link"
            size="sm"
            onClick={() => setSessionEpoch((e) => e + 1)}
            title="Reconnect interactive shell"
          >
            Reconnect
          </Button>
        ) : null}
      </div>

      {isApiProject && provisioning ? (
        <div className="term-banner term-banner--info">
          <Spinner size="sm" aria-label="Provisioning" /> Provisioning sandbox…
        </div>
      ) : null}

      {isApiProject && status === 'stopped' ? (
        <div className="term-banner term-banner--warn">
          Sandbox is stopped.{' '}
          <Button variant="link" isInline size="sm" onClick={() => void doRecreate()} isLoading={recreating}>
            Recreate sandbox
          </Button>
        </div>
      ) : null}

      {isApiProject && (needsRecreate || (status === 'error' && !provisioning)) ? (
        <div className="term-banner term-banner--error">
          <span>{p?.sandboxError || 'Sandbox unavailable.'} Recreate to continue.</span>
          <Button variant="primary" size="sm" onClick={() => void doRecreate()} isLoading={recreating}>
            Recreate sandbox
          </Button>
        </div>
      ) : null}

      {useInteractive && !sandboxReady && !provisioning && status !== 'error' ? (
        <div className="term-banner term-banner--warn">
          Waiting for sandbox to be running before opening interactive shell…
        </div>
      ) : null}

      <div className="term-session-strip" role="tablist" aria-label="Terminal sessions">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`term-session-pill ${s.id === active?.id ? 'is-active' : ''}`}
            role="tab"
            aria-selected={s.id === active?.id}
            onClick={() => {
              setActiveId(s.id)
              requestAnimationFrame(() => {
                const h = handlesRef.current[s.id]
                h?.focus()
                if (h && 'fit' in h && typeof h.fit === 'function') h.fit()
              })
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') setActiveId(s.id)
            }}
            tabIndex={0}
          >
            <span>{s.name}</span>
            {sessions.length > 1 && (
              <button
                type="button"
                className="term-session-close"
                aria-label={`Close ${s.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  closeSession(s.id)
                }}
              >
                ×
              </button>
            )}
          </div>
        ))}
        <Button variant="plain" size="sm" onClick={() => addSession()} aria-label="New shell">
          +
        </Button>
      </div>

      <div className="term-xterm-stack">
        {sessions.map((s) => (
          <div
            key={`${s.id}-${sessionEpoch}`}
            className={`term-xterm-pane${s.id === active?.id ? ' is-active' : ''}`}
            hidden={s.id !== active?.id}
          >
            {useInteractive && currentProjectId && sandboxReady ? (
              <InteractiveSandboxTerminal
                projectId={currentProjectId}
                cmd={s.cmd}
                cwd="/workspace"
                enabled={inputEnabled && s.id === active?.id}
                onReady={(h) => {
                  handlesRef.current[s.id] = h
                }}
                onStatus={(st, detail) => {
                  if (s.id === active?.id) setWsStatus(detail ? `${st}: ${detail}` : st)
                }}
              />
            ) : useInteractive && currentProjectId ? (
              <div className="term-waiting">
                <Spinner size="lg" />
                <p>Sandbox must be running for interactive shell.</p>
              </div>
            ) : (
              <SandboxXterm
                prompt={`demo@${p?.slug || 'local'}:~$ `}
                enabled={s.id === active?.id}
                welcomeLines={[
                  '\x1b[90mLocal demo terminal (line mode)\x1b[0m',
                  '\x1b[90mAPI projects use interactive PTY for opencode etc.\x1b[0m',
                ]}
                onCommand={async (line) => {
                  const h = handlesRef.current[s.id] as SandboxXtermHandle | undefined
                  h?.write(`\x1b[90mdemo: would run \`${line}\`\x1b[0m\r\n`)
                }}
                onReady={(h) => {
                  handlesRef.current[s.id] = h
                }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
