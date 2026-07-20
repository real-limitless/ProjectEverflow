import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'

export type SandboxXtermHandle = {
  /** Prefill the current input line (does not submit). */
  setLine: (text: string) => void
  /** Write raw data to the terminal (during/after a command). */
  write: (text: string) => void
  /** Write a line then re-show the prompt (idle only). */
  writeln: (text: string) => void
  /** Clear screen and re-prompt. */
  clear: () => void
  focus: () => void
}

interface SandboxXtermProps {
  prompt: string
  enabled: boolean
  onCommand: (line: string, signal: AbortSignal) => Promise<void>
  onReady?: (handle: SandboxXtermHandle) => void
  className?: string
  welcomeLines?: string[]
}

/**
 * Line-oriented xterm shell: local echo + history; commands via onCommand.
 */
export function SandboxXterm({
  prompt,
  enabled,
  onCommand,
  onReady,
  className,
  welcomeLines,
}: SandboxXtermProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const lineRef = useRef('')
  const historyRef = useRef<string[]>([])
  const histIdxRef = useRef(-1)
  const busyRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const enabledRef = useRef(enabled)
  const promptRef = useRef(prompt)
  const onCommandRef = useRef(onCommand)

  enabledRef.current = enabled
  promptRef.current = prompt
  onCommandRef.current = onCommand

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily:
        'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
      fontSize: 13,
      lineHeight: 1.25,
      scrollback: 5000,
      convertEol: true,
      allowProposedApi: true,
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
    fit.fit()
    termRef.current = term
    fitRef.current = fit

    const writePrompt = () => {
      term.write(`\r\n\x1b[32m${promptRef.current}\x1b[0m`)
    }

    const redrawLine = () => {
      term.write('\r\x1b[K')
      term.write(`\x1b[32m${promptRef.current}\x1b[0m${lineRef.current}`)
    }

    const handle: SandboxXtermHandle = {
      setLine: (text: string) => {
        lineRef.current = text
        histIdxRef.current = -1
        redrawLine()
      },
      write: (text: string) => {
        term.write(text)
      },
      writeln: (text: string) => {
        term.writeln('')
        term.writeln(text)
        writePrompt()
        lineRef.current = ''
      },
      clear: () => {
        term.clear()
        term.write(`\x1b[32m${promptRef.current}\x1b[0m${lineRef.current}`)
      },
      focus: () => term.focus(),
    }
    onReady?.(handle)

    for (const w of welcomeLines || []) {
      term.writeln(w)
    }
    term.write(`\x1b[32m${promptRef.current}\x1b[0m`)

    const runLine = async (raw: string) => {
      const line = raw.trimEnd()
      if (!line.trim()) {
        writePrompt()
        lineRef.current = ''
        return
      }
      historyRef.current.push(line)
      if (historyRef.current.length > 200) historyRef.current.shift()
      histIdxRef.current = -1
      lineRef.current = ''
      busyRef.current = true
      const ac = new AbortController()
      abortRef.current = ac
      try {
        await onCommandRef.current(line, ac.signal)
      } catch (e) {
        if (!ac.signal.aborted) {
          const msg = e instanceof Error ? e.message : String(e)
          term.writeln(`\x1b[31m${msg}\x1b[0m`)
        }
      } finally {
        busyRef.current = false
        abortRef.current = null
        if (!ac.signal.aborted) {
          writePrompt()
        }
      }
    }

    const onData = (data: string) => {
      if (!enabledRef.current && !busyRef.current) return

      let i = 0
      while (i < data.length) {
        const ch = data[i]
        const code = ch.charCodeAt(0)

        // Ctrl+C
        if (code === 3) {
          if (busyRef.current && abortRef.current) {
            abortRef.current.abort()
            term.write('^C\r\n')
            busyRef.current = false
            abortRef.current = null
            writePrompt()
            lineRef.current = ''
          } else if (!busyRef.current) {
            term.write('^C')
            writePrompt()
            lineRef.current = ''
          }
          i += 1
          continue
        }

        if (busyRef.current) {
          i += 1
          continue
        }

        // Ctrl+L
        if (code === 12) {
          handle.clear()
          i += 1
          continue
        }

        // Ctrl+U
        if (code === 21) {
          lineRef.current = ''
          redrawLine()
          i += 1
          continue
        }

        // Enter
        if (ch === '\r' || ch === '\n') {
          term.write('\r\n')
          void runLine(lineRef.current)
          i += 1
          continue
        }

        // Backspace
        if (code === 127 || code === 8) {
          if (lineRef.current.length > 0) {
            lineRef.current = lineRef.current.slice(0, -1)
            term.write('\b \b')
          }
          i += 1
          continue
        }

        // Escape sequences
        if (ch === '\x1b') {
          const seq = data.slice(i)
          if (seq.startsWith('\x1b[A')) {
            // Up
            i += 3
            const hist = historyRef.current
            if (!hist.length) continue
            if (histIdxRef.current < 0) histIdxRef.current = hist.length
            histIdxRef.current = Math.max(0, histIdxRef.current - 1)
            lineRef.current = hist[histIdxRef.current] ?? ''
            redrawLine()
            continue
          }
          if (seq.startsWith('\x1b[B')) {
            // Down
            i += 3
            const hist = historyRef.current
            if (histIdxRef.current < 0) continue
            histIdxRef.current += 1
            if (histIdxRef.current >= hist.length) {
              histIdxRef.current = -1
              lineRef.current = ''
            } else {
              lineRef.current = hist[histIdxRef.current] ?? ''
            }
            redrawLine()
            continue
          }
          const m = seq.match(/^\x1b\[[0-9;]*[A-Za-z]/)
          if (m) {
            i += m[0].length
            continue
          }
          i += 1
          continue
        }

        // Printable UTF-16 unit (good enough for paste of ASCII/unicode BMP)
        if (code >= 32) {
          lineRef.current += ch
          term.write(ch)
        }
        i += 1
      }
    }

    const disp = term.onData(onData)

    const ro = new ResizeObserver(() => {
      try {
        fit.fit()
      } catch {
        /* ignore */
      }
    })
    ro.observe(host)

    requestAnimationFrame(() => {
      try {
        fit.fit()
        term.focus()
      } catch {
        /* ignore */
      }
    })

    return () => {
      disp.dispose()
      ro.disconnect()
      abortRef.current?.abort()
      term.dispose()
      termRef.current = null
      fitRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    promptRef.current = prompt
  }, [prompt])

  return (
    <div
      ref={hostRef}
      className={className ?? 'sandbox-xterm'}
      onClick={() => termRef.current?.focus()}
    />
  )
}
