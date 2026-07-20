import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Label, Spinner } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import {
  ApiError,
  execShellLine,
  getSandboxStatus,
  recreateSandbox,
} from '@/lib/api'
import { waitForSandbox } from '@/lib/sandboxPoll'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { SandboxXterm, type SandboxXtermHandle } from './SandboxXterm'

type SessionMeta = {
  id: string
  name: string
}

function newSessionMeta(index: number): SessionMeta {
  return {
    id: `sh-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 5)}`,
    name: index === 0 ? 'bash' : `shell-${index + 1}`,
  }
}

const STATUS_COLOR: Record<string, 'blue' | 'green' | 'orange' | 'red' | 'grey' | 'purple'> = {
  pending: 'blue',
  creating: 'purple',
  running: 'green',
  stopped: 'grey',
  error: 'red',
  destroyed: 'grey',
}

function shellQuote(s: string): string {
  return `'${s.replace(/'/g, `'\"'\"'`)}'`
}

async function execShellLineWithSignal(
  projectId: string,
  line: string,
  signal: AbortSignal,
  cwd: string,
): Promise<{ stdout: string; stderr: string; exit_code: number }> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const onAbort = () => reject(new DOMException('Aborted', 'AbortError'))
    signal.addEventListener('abort', onAbort, { once: true })
    void execShellLine(projectId, line, { cwd, timeout_seconds: 120 })
      .then((r) => {
        signal.removeEventListener('abort', onAbort)
        resolve(r)
      })
      .catch((e) => {
        signal.removeEventListener('abort', onAbort)
        reject(e)
      })
  })
}

function formatOutput(result: {
  stdout: string
  stderr: string
  exit_code: number
}): string {
  let out = ''
  if (result.stdout) {
    const s = result.stdout.replace(/\r\n/g, '\n')
    out += s.endsWith('\n') ? s : s + '\n'
  }
  if (result.stderr) {
    const s = result.stderr.replace(/\r\n/g, '\n')
    const body = s.endsWith('\n') ? s : s + '\n'
    out += `\x1b[31m${body}\x1b[0m`
  }
  if (result.exit_code !== 0) {
    out += `\x1b[90mexit ${result.exit_code}\x1b[0m\n`
  }
  return out.replace(/\n/g, '\r\n')
}

export function TerminalPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const prefill = usePlaygroundStore((s) => s.terminalPrefill)
  const clearTerminalPrefill = usePlaygroundStore((s) => s.clearTerminalPrefill)
  const patchProjectSandbox = usePlaygroundStore((s) => s.patchProjectSandbox)
  const p = getProject(currentProjectId)
  void catalogVersion

  const [sessions, setSessions] = useState<SessionMeta[]>(() => [newSessionMeta(0)])
  const [activeId, setActiveId] = useState(() => sessions[0]?.id ?? '')
  const [recreating, setRecreating] = useState(false)
  const [cwdBySession, setCwdBySession] = useState<Record<string, string>>({})
  const handlesRef = useRef<Record<string, SandboxXtermHandle | null>>({})

  useEffect(() => {
    const first = newSessionMeta(0)
    setSessions([first])
    setActiveId(first.id)
    setCwdBySession({})
    handlesRef.current = {}
  }, [currentProjectId])

  const active = sessions.find((s) => s.id === activeId) ?? sessions[0]
  const status = p?.sandboxStatus || 'unknown'
  const sandboxReady = Boolean(p?.fromApi && status === 'running')
  const needsRecreate =
    Boolean(p?.fromApi) &&
    (status === 'error' ||
      status === 'destroyed' ||
      (status !== 'running' &&
        status !== 'pending' &&
        status !== 'creating' &&
        status !== 'stopped'))
  const provisioning = status === 'pending' || status === 'creating'
  const slug = p?.slug || p?.name || 'project'
  const cwd = (active && cwdBySession[active.id]) || '/workspace'

  const prompt = useMemo(() => {
    const shortCwd =
      cwd === '/workspace' || cwd === '/workspace/'
        ? '~'
        : cwd.replace(/^\/workspace\/?/, '~/') || '~'
    return `sandbox@${slug}:${shortCwd}$ `
  }, [slug, cwd])

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
    const id = window.setInterval(() => void syncStatus(), 3000)
    return () => window.clearInterval(id)
  }, [p?.fromApi, currentProjectId, syncStatus])

  useEffect(() => {
    if (!prefill || !active) return
    const h = handlesRef.current[active.id]
    if (h) {
      h.setLine(prefill)
      h.focus()
    }
    clearTerminalPrefill()
  }, [prefill, active, clearTerminalPrefill])

  const doRecreate = async () => {
    if (!p?.fromApi || !currentProjectId || recreating) return
    setRecreating(true)
    const h = active ? handlesRef.current[active.id] : null
    h?.write('\r\n\x1b[33mrecreating sandbox…\x1b[0m\r\n')
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
        h?.writeln('\x1b[32msandbox ready\x1b[0m')
      } else {
        pushToast(st.error || 'Sandbox recreate failed', { kind: 'danger' })
        h?.writeln(`\x1b[31m${st.error || 'recreate failed'}\x1b[0m`)
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'recreate failed'
      pushToast(msg, { kind: 'danger' })
      h?.writeln(`\x1b[31m${msg}\x1b[0m`)
    } finally {
      setRecreating(false)
    }
  }

  const makeOnCommand = useCallback(
    (sessionId: string) => {
      return async (line: string, signal: AbortSignal) => {
        const write = (text: string) => {
          handlesRef.current[sessionId]?.write(text)
        }

        if (!p?.fromApi) {
          write(`\x1b[90mdemo: would run \`${line}\` in sandbox\x1b[0m\r\n`)
          return
        }

        await syncStatus()
        if (signal.aborted) return
        const latest = getProject(currentProjectId)
        if (latest?.sandboxStatus !== 'running') {
          const msg =
            latest?.sandboxError ||
            `sandbox not ready (status=${latest?.sandboxStatus || 'unknown'}). Use Recreate if missing.`
          write(`\x1b[31m${msg}\x1b[0m\r\n`)
          return
        }

        const sessionCwd = cwdBySession[sessionId] || '/workspace'
        const trimmed = line.trim()

        // Client-side cd for prompt / cwd passthrough
        if (trimmed === 'cd' || trimmed.startsWith('cd ')) {
          const arg = trimmed === 'cd' ? '/workspace' : trimmed.slice(3).trim() || '/workspace'
          let next = arg
          if (arg === '~' || arg === '') next = '/workspace'
          else if (arg.startsWith('/')) next = arg
          else if (arg === '..') {
            const parts = sessionCwd.split('/').filter(Boolean)
            parts.pop()
            next = parts.length ? `/${parts.join('/')}` : '/workspace'
          } else {
            next = `${sessionCwd.replace(/\/$/, '')}/${arg}`
          }
          try {
            const check = await execShellLineWithSignal(
              p.id,
              `test -d ${shellQuote(next)}`,
              signal,
              sessionCwd,
            )
            if (signal.aborted) return
            if (check.exit_code === 0) {
              setCwdBySession((m) => ({ ...m, [sessionId]: next }))
            } else {
              write(`\x1b[31mcd: no such directory: ${arg}\x1b[0m\r\n`)
            }
          } catch (e) {
            if (signal.aborted) return
            write(`\x1b[31m${e instanceof Error ? e.message : String(e)}\x1b[0m\r\n`)
          }
          return
        }

        try {
          const result = await execShellLineWithSignal(p.id, line, signal, sessionCwd)
          if (signal.aborted) return
          write(formatOutput(result))
        } catch (e) {
          if (signal.aborted) return
          const msg =
            e instanceof ApiError
              ? e.message
              : e instanceof Error
                ? e.message
                : 'exec failed'
          const missing =
            e instanceof ApiError &&
            (e.status === 404 ||
              e.status === 409 ||
              /not found on agent|recreate/i.test(msg))
          if (missing && currentProjectId) {
            patchProjectSandbox(currentProjectId, {
              sandboxStatus: 'error',
              sandboxError: msg,
            })
            write(
              `\x1b[31m${msg}\x1b[0m\r\n\x1b[90mSandbox missing — use Recreate sandbox above.\x1b[0m\r\n`,
            )
          } else {
            write(`\x1b[31m${msg}\x1b[0m\r\n`)
          }
        }
      }
    },
    [p, currentProjectId, cwdBySession, syncStatus, patchProjectSandbox],
  )

  const addSession = () => {
    const s = newSessionMeta(sessions.length)
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

  const inputEnabled = !recreating && (p?.fromApi ? sandboxReady : true)

  const welcome = useMemo(() => {
    const lines = [
      '\x1b[90mEverflow sandbox terminal · xterm.js\x1b[0m',
      p?.fromApi
        ? `\x1b[90m${p.name} · ${p.sandboxName || 'sandbox'} · ${status}\x1b[0m`
        : '\x1b[90mlocal demo — commands are not run on a remote sandbox\x1b[0m',
    ]
    if (p?.fromApi && !sandboxReady) {
      lines.push(
        `\x1b[33mwaiting for sandbox (${status})${p.sandboxError ? `: ${p.sandboxError}` : ''}\x1b[0m`,
      )
    }
    return lines
  }, [p, status, sandboxReady])

  return (
    <div className="term-wrap term-wrap--xterm">
      <div className="term-toolbar">
        <span>
          sandbox · {p?.name || '—'}
          {p?.fromApi ? ` · ${p.sandboxName || 'unprovisioned'}` : ''} ·{' '}
          {sessions.length} shell{sessions.length === 1 ? '' : 's'}
        </span>
        {p?.fromApi ? (
          <Label color={STATUS_COLOR[status] || 'grey'} isCompact title={p.sandboxError || status}>
            {status}
          </Label>
        ) : (
          <Label color="grey" isCompact>
            local demo
          </Label>
        )}
        <Button variant="link" size="sm" onClick={clearActive}>
          Clear
        </Button>
      </div>

      {p?.fromApi && provisioning ? (
        <div className="term-banner term-banner--info">
          <Spinner size="sm" aria-label="Provisioning" /> Provisioning sandbox…
        </div>
      ) : null}

      {p?.fromApi && status === 'stopped' ? (
        <div className="term-banner term-banner--warn">
          Sandbox is stopped.{' '}
          <Button variant="link" isInline size="sm" onClick={() => void doRecreate()} isLoading={recreating}>
            Recreate sandbox
          </Button>
        </div>
      ) : null}

      {p?.fromApi && (needsRecreate || (status === 'error' && !provisioning)) ? (
        <div className="term-banner term-banner--error">
          <span>
            {p.sandboxError || 'Sandbox unavailable on agent.'} Recreate to continue.
          </span>
          <Button variant="primary" size="sm" onClick={() => void doRecreate()} isLoading={recreating}>
            Recreate sandbox
          </Button>
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
              requestAnimationFrame(() => handlesRef.current[s.id]?.focus())
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
        <Button variant="plain" size="sm" onClick={addSession} aria-label="New shell">
          +
        </Button>
      </div>

      <div className="term-xterm-stack">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`term-xterm-pane${s.id === active?.id ? ' is-active' : ''}`}
            hidden={s.id !== active?.id}
          >
            <SandboxXterm
              prompt={s.id === active?.id ? prompt : `sandbox@${slug}:~$ `}
              enabled={inputEnabled && s.id === active?.id}
              welcomeLines={s.id === sessions[0]?.id ? welcome : ['\x1b[90mnew shell\x1b[0m']}
              onCommand={makeOnCommand(s.id)}
              onReady={(h) => {
                handlesRef.current[s.id] = h
              }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
