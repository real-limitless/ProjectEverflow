import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { sandboxShellWsUrl } from '@/lib/api'

export type InteractiveTerminalHandle = {
  focus: () => void
  write: (data: string) => void
  clear: () => void
  sendLine: (line: string) => void
  fit: () => void
}

interface InteractiveSandboxTerminalProps {
  projectId: string
  cmd?: string
  cwd?: string
  enabled: boolean
  onReady?: (handle: InteractiveTerminalHandle) => void
  onStatus?: (status: 'connecting' | 'ready' | 'closed' | 'error', detail?: string) => void
  className?: string
}

function decodeOutput(msg: { data?: string; encoding?: string }): string {
  if (!msg.data) return ''
  if (msg.encoding === 'base64') {
    try {
      const bin = atob(msg.data)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      return new TextDecoder('utf-8').decode(bytes)
    } catch {
      return msg.data
    }
  }
  return msg.data
}

/** Measure host and resize xterm so cols/rows match the panel (not default 80×24). */
function measureAndResize(term: Terminal, host: HTMLElement, fit: FitAddon): { cols: number; rows: number } {
  const w = host.clientWidth
  const h = host.clientHeight
  if (w < 20 || h < 12) {
    return { cols: term.cols, rows: term.rows }
  }

  // Prefer FitAddon when cell metrics are ready
  try {
    fit.fit()
  } catch {
    /* ignore */
  }

  // Manual fallback / correction using cell size + host box
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const core = (term as any)._core
    const cell = core?._renderService?.dimensions?.css?.cell
    const el = term.element
    if (cell?.width > 0 && cell?.height > 0 && el) {
      const style = window.getComputedStyle(el)
      const padX =
        (parseInt(style.paddingLeft || '0', 10) || 0) +
        (parseInt(style.paddingRight || '0', 10) || 0)
      const padY =
        (parseInt(style.paddingTop || '0', 10) || 0) +
        (parseInt(style.paddingBottom || '0', 10) || 0)
      // FitAddon subtracts ~14 for scrollbar; match that so we don't overflow
      const scrollBar = term.options.scrollback === 0 ? 0 : 14
      const cols = Math.max(2, Math.floor((w - padX - scrollBar) / cell.width))
      const rows = Math.max(1, Math.floor((h - padY) / cell.height))
      if (cols !== term.cols || rows !== term.rows) {
        term.resize(cols, rows)
      }
    }
  } catch {
    /* ignore */
  }

  return { cols: term.cols, rows: term.rows }
}

function waitForHostSize(host: HTMLElement, minW = 80, minH = 40, maxFrames = 60): Promise<boolean> {
  return new Promise((resolve) => {
    let frames = 0
    const tick = () => {
      if (host.clientWidth >= minW && host.clientHeight >= minH) {
        resolve(true)
        return
      }
      frames += 1
      if (frames >= maxFrames) {
        resolve(host.clientWidth > 0 && host.clientHeight > 0)
        return
      }
      requestAnimationFrame(tick)
    }
    tick()
  })
}

/**
 * Raw interactive PTY over WebSocket. Fills parent; FitAddon + resize frames.
 * Critical: measure panel size BEFORE the guest process starts (no live PTY
 * resize in microsandbox — size is applied via stty + COLUMNS/LINES at start).
 */
export function InteractiveSandboxTerminal({
  projectId,
  cmd,
  cwd = '/workspace',
  enabled,
  onReady,
  onStatus,
  className,
}: InteractiveSandboxTerminalProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const enabledRef = useRef(enabled)
  const lastSizeRef = useRef({ cols: 0, rows: 0 })
  enabledRef.current = enabled

  useEffect(() => {
    const host = hostRef.current
    if (!host || !projectId) return

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily:
        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
      fontSize: 13,
      lineHeight: 1.2,
      scrollback: 8000,
      convertEol: true,
      allowProposedApi: true,
      // Seed large enough that first paint isn't 80-col; fit replaces these
      cols: 120,
      rows: 32,
      theme: {
        background: '#1a1d21',
        foreground: '#e0e0e0',
        cursor: '#f0f0f0',
        cursorAccent: '#1a1d21',
        selectionBackground: 'rgba(100, 149, 237, 0.35)',
        black: '#1a1d21',
        red: '#f87171',
        green: '#4ade80',
        yellow: '#fbbf24',
        blue: '#60a5fa',
        magenta: '#c084fc',
        cyan: '#22d3ee',
        white: '#e5e5e5',
        brightBlack: '#6b7280',
        brightRed: '#fca5a5',
        brightGreen: '#86efac',
        brightYellow: '#fde047',
        brightBlue: '#93c5fd',
        brightMagenta: '#d8b4fe',
        brightCyan: '#67e8f9',
        brightWhite: '#ffffff',
      },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(host)
    termRef.current = term
    fitRef.current = fit

    const sendResize = (force = false) => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      const { cols, rows } = term
      if (cols < 2 || rows < 1) return
      if (
        !force &&
        cols === lastSizeRef.current.cols &&
        rows === lastSizeRef.current.rows
      ) {
        return
      }
      lastSizeRef.current = { cols, rows }
      ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    }

    const doFit = (forceSend = false) => {
      try {
        if (host.clientWidth < 10 || host.clientHeight < 10) return
        measureAndResize(term, host, fit)
        sendResize(forceSend)
      } catch {
        /* ignore */
      }
    }

    const handle: InteractiveTerminalHandle = {
      focus: () => term.focus(),
      write: (d) => term.write(d),
      clear: () => term.clear(),
      sendLine: (line) => {
        const ws = wsRef.current
        if (ws && ws.readyState === WebSocket.OPEN) {
          const payload = line.endsWith('\n') || line.endsWith('\r') ? line : line + '\r'
          ws.send(JSON.stringify({ type: 'input', data: payload }))
        }
      },
      fit: () => doFit(true),
    }
    onReady?.(handle)

    let closed = false
    let fitTimer: number | null = null
    let reconnectTimer: number | null = null
    let pingTimer: number | null = null
    let reconnectAttempt = 0
    let intentionalClose = false
    // Skip auto-reconnect after intentional process exit when a custom cmd was set.
    let suppressReconnect = false
    const PING_MS = 25_000
    const RECONNECT_BASE_MS = 500
    const RECONNECT_MAX_MS = 10_000

    const scheduleFit = () => {
      if (fitTimer != null) window.clearTimeout(fitTimer)
      fitTimer = window.setTimeout(() => {
        fitTimer = null
        doFit()
      }, 40)
    }

    const clearPing = () => {
      if (pingTimer != null) {
        window.clearInterval(pingTimer)
        pingTimer = null
      }
    }

    const startPing = (ws: WebSocket) => {
      clearPing()
      pingTimer = window.setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(JSON.stringify({ type: 'ping' }))
          } catch {
            /* ignore */
          }
        }
      }, PING_MS)
    }

    const scheduleReconnect = (reason: string) => {
      if (closed || suppressReconnect) return
      if (reconnectTimer != null) return
      const delay = Math.min(
        RECONNECT_MAX_MS,
        RECONNECT_BASE_MS * 2 ** Math.min(reconnectAttempt, 5),
      )
      reconnectAttempt += 1
      term.writeln(
        `\r\n\x1b[90m[disconnected${reason ? `: ${reason}` : ''}] reconnecting in ${Math.round(delay / 1000)}s…\x1b[0m`,
      )
      onStatus?.('closed', reason)
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        void connect({ isReconnect: true })
      }, delay)
    }

    const connect = async (opts?: { isReconnect?: boolean }) => {
      if (closed) return
      if (reconnectTimer != null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      suppressReconnect = false
      intentionalClose = false
      onStatus?.('connecting')
      if (opts?.isReconnect) {
        term.writeln('\x1b[90mreconnecting to sandbox shell…\x1b[0m')
      } else {
        term.writeln('\x1b[90mconnecting to sandbox shell…\x1b[0m')
      }

      // Wait until the dock panel has a real box so initial cols/rows are correct.
      await waitForHostSize(host)
      if (closed) return
      measureAndResize(term, host, fit)
      // One more frame after fonts/layout settle
      await new Promise<void>((r) => requestAnimationFrame(() => r()))
      if (closed) return
      measureAndResize(term, host, fit)

      const url = sandboxShellWsUrl(projectId, { cmd, cwd })
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttempt = 0
        startPing(ws)
        // Server waits for first resize before starting the guest process
        measureAndResize(term, host, fit)
        const { cols, rows } = term
        lastSizeRef.current = { cols, rows }
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
        // Repeat after layout in case dock was animating
        requestAnimationFrame(() => {
          measureAndResize(term, host, fit)
          sendResize(true)
          requestAnimationFrame(() => {
            measureAndResize(term, host, fit)
            sendResize(true)
          })
        })
      }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as {
            type: string
            data?: string
            encoding?: string
            message?: string
            code?: number
            mode?: string
            need_size?: boolean
            cols?: number
            rows?: number
          }
          if (msg.type === 'ready') {
            // Server is waiting for size — send measured dimensions immediately
            measureAndResize(term, host, fit)
            sendResize(true)
            onStatus?.('ready', msg.mode)
            term.writeln(`\x1b[90mconnected (${msg.mode || 'pty'})\x1b[0m`)
            term.focus()
          } else if (msg.type === 'started') {
            onStatus?.('ready', msg.mode || 'pty')
            // Keep pushing size after process start for live guest stty
            doFit(true)
            term.focus()
          } else if (msg.type === 'output') {
            term.write(decodeOutput(msg))
          } else if (msg.type === 'pong') {
            /* keepalive ack */
          } else if (msg.type === 'error') {
            onStatus?.('error', msg.message)
            term.writeln(`\r\n\x1b[31m${msg.message || 'error'}\x1b[0m`)
          } else if (msg.type === 'exit') {
            term.writeln(`\r\n\x1b[90m[process exited ${msg.code ?? '?'}]\x1b[0m`)
            onStatus?.('closed', String(msg.code ?? ''))
            // Default interactive shell: restart. Custom cmd (e.g. one-shot): stop.
            if (!cmd && !closed) {
              intentionalClose = true
              try {
                ws.close()
              } catch {
                /* ignore */
              }
              scheduleReconnect('shell exited')
            } else {
              suppressReconnect = true
            }
          }
        } catch {
          term.write(String(ev.data))
        }
      }

      ws.onerror = () => {
        // onclose will schedule reconnect; avoid double banners
        onStatus?.('error', 'WebSocket error')
      }

      ws.onclose = () => {
        clearPing()
        if (wsRef.current === ws) wsRef.current = null
        if (closed || intentionalClose) {
          intentionalClose = false
          return
        }
        scheduleReconnect('connection lost')
      }
    }

    void connect()

    const dataDisp = term.onData((data) => {
      if (!enabledRef.current) return
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    // Observe host + ancestors so dock sash / window resize reflows the PTY
    const ro = new ResizeObserver(() => scheduleFit())
    ro.observe(host)
    let el: HTMLElement | null = host.parentElement
    for (let i = 0; i < 8 && el; i++) {
      ro.observe(el)
      el = el.parentElement
    }

    window.addEventListener('resize', scheduleFit)

    // Initial local fit (WS may not be open yet)
    scheduleFit()
    requestAnimationFrame(() => {
      scheduleFit()
      term.focus()
    })

    return () => {
      closed = true
      suppressReconnect = true
      if (fitTimer != null) window.clearTimeout(fitTimer)
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer)
      clearPing()
      dataDisp.dispose()
      ro.disconnect()
      window.removeEventListener('resize', scheduleFit)
      try {
        wsRef.current?.close()
      } catch {
        /* ignore */
      }
      wsRef.current = null
      term.dispose()
      termRef.current = null
      fitRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, cmd, cwd])

  // When the shell tab becomes active (enabled) or the dock pane is shown again
  // (keep-alive: host was 0×0 under display:none), re-fit and push winsize.
  useEffect(() => {
    if (!enabled) return
    const host = hostRef.current
    if (!host) return

    const run = () => {
      const term = termRef.current
      const fit = fitRef.current
      if (!host || !term || !fit) return
      if (host.clientWidth < 10 || host.clientHeight < 10) return
      try {
        measureAndResize(term, host, fit)
        const ws = wsRef.current
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(
            JSON.stringify({
              type: 'resize',
              cols: term.cols,
              rows: term.rows,
            }),
          )
          lastSizeRef.current = { cols: term.cols, rows: term.rows }
        }
        term.focus()
      } catch {
        /* ignore */
      }
    }

    const t1 = window.setTimeout(run, 30)
    const t2 = window.setTimeout(run, 120)
    const t3 = window.setTimeout(run, 300)

    // Dock keep-alive: pane may reappear without `enabled` flipping; observe host
    // until it has a real box again after being hidden.
    const ro = new ResizeObserver(() => run())
    ro.observe(host)

    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
      window.clearTimeout(t3)
      ro.disconnect()
    }
  }, [enabled])

  return (
    <div
      ref={hostRef}
      className={className ?? 'sandbox-xterm'}
      onClick={() => termRef.current?.focus()}
    />
  )
}
