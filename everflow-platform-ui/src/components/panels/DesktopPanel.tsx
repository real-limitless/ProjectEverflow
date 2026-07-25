import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Spinner } from '@patternfly/react-core'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  createPreviewEndpoint,
  isDemoMode,
  previewIframeSrc,
  resizeSandboxDesktop,
  type PreviewEndpoint,
} from '@/lib/api'
import { usePlaygroundStore } from '@/store/playgroundStore'

const DESKTOP_PORT = 6080
const VNC_PATH = '/vnc.html'
/** Debounce panel resize → guest xrandr (ms). */
const RESIZE_DEBOUNCE_MS = 350
const MIN_W = 640
const MIN_H = 480
const MAX_W = 3840
const MAX_H = 2160

function desktopIframeSrc(endpoint: PreviewEndpoint): string {
  const base = previewIframeSrc(endpoint, VNC_PATH)
  try {
    const u = new URL(base)
    u.searchParams.set('autoconnect', '1')
    // scale fills the iframe while guest FB is matched via resize API
    u.searchParams.set('resize', 'scale')
    return u.href
  } catch {
    const join = base.includes('?') ? '&' : '?'
    return `${base}${join}autoconnect=1&resize=scale`
  }
}

function clampEven(n: number, min: number, max: number): number {
  let v = Math.round(n)
  v = Math.max(min, Math.min(max, v))
  return v - (v % 2)
}

/**
 * Live Linux desktop via guest noVNC (port 6080), framed through the preview proxy.
 * Panel size is pushed to the guest X framebuffer so the desktop tracks tab/dock resize.
 */
export function DesktopPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const project = getProject(projectId)
  void catalogVersion

  const demo = isDemoMode()
  const sandboxRunning = project?.sandboxStatus === 'running'
  const sandboxStatus = project?.sandboxStatus || (project ? 'unknown' : null)

  const [iframeSrc, setIframeSrc] = useState<string | null>(null)
  const [minting, setMinting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [fbLabel, setFbLabel] = useState<string | null>(null)
  const remintTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const resizeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastSize = useRef<{ w: number; h: number } | null>(null)
  const frameHostRef = useRef<HTMLDivElement | null>(null)
  const resizeInflight = useRef(false)
  const pendingSize = useRef<{ w: number; h: number } | null>(null)

  const mint = useCallback(async () => {
    if (!projectId || !sandboxRunning) return
    setMinting(true)
    setError(null)
    try {
      const ep = await createPreviewEndpoint(projectId, DESKTOP_PORT)
      setIframeSrc(desktopIframeSrc(ep))
      if (remintTimer.current) clearTimeout(remintTimer.current)
      const ms = Math.max(30_000, ep.expires_at * 1000 - Date.now() - 60_000)
      remintTimer.current = setTimeout(() => {
        void mint()
      }, ms)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open desktop')
      setIframeSrc(null)
    } finally {
      setMinting(false)
    }
  }, [projectId, sandboxRunning])

  const pushResize = useCallback(
    async (width: number, height: number) => {
      if (!projectId || !sandboxRunning) return
      const w = clampEven(width, MIN_W, MAX_W)
      const h = clampEven(height, MIN_H, MAX_H)
      if (w < MIN_W || h < MIN_H) return
      const prev = lastSize.current
      if (prev && prev.w === w && prev.h === h) return

      if (resizeInflight.current) {
        pendingSize.current = { w, h }
        return
      }
      resizeInflight.current = true
      try {
        const res = await resizeSandboxDesktop(projectId, w, h)
        if (res.ok) {
          lastSize.current = { w: res.width, h: res.height }
          setFbLabel(`${res.width}×${res.height}`)
        }
      } catch {
        // Best-effort: scale mode still fills the iframe if resize fails
      } finally {
        resizeInflight.current = false
        const next = pendingSize.current
        pendingSize.current = null
        if (next && (next.w !== lastSize.current?.w || next.h !== lastSize.current?.h)) {
          void pushResize(next.w, next.h)
        }
      }
    },
    [projectId, sandboxRunning],
  )

  const scheduleResize = useCallback(
    (width: number, height: number) => {
      if (resizeTimer.current) clearTimeout(resizeTimer.current)
      resizeTimer.current = setTimeout(() => {
        void pushResize(width, height)
      }, RESIZE_DEBOUNCE_MS)
    },
    [pushResize],
  )

  useEffect(() => {
    if (!sandboxRunning) {
      setIframeSrc(null)
      setError(null)
      setFbLabel(null)
      lastSize.current = null
      if (remintTimer.current) clearTimeout(remintTimer.current)
      return
    }
    void mint()
    return () => {
      if (remintTimer.current) clearTimeout(remintTimer.current)
    }
  }, [sandboxRunning, mint])

  // Observe the noVNC host so dock sash / window / tab resize reflows the guest desktop.
  useEffect(() => {
    if (!iframeSrc || !sandboxRunning) return
    const el = frameHostRef.current
    if (!el || typeof ResizeObserver === 'undefined') return

    const measure = () => {
      const r = el.getBoundingClientRect()
      if (r.width >= 32 && r.height >= 32) {
        scheduleResize(r.width, r.height)
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
      if (resizeTimer.current) clearTimeout(resizeTimer.current)
    }
  }, [iframeSrc, sandboxRunning, scheduleResize])

  if (demo) {
    return (
      <EmptySplash
        title="Desktop unavailable in demo"
        body="Open an API project with a running sandbox to use the noVNC webtop."
      />
    )
  }

  if (!projectId || !project) {
    return (
      <EmptySplash
        title="No project open"
        body="Open a project to connect to its sandbox desktop."
      />
    )
  }

  if (!sandboxRunning) {
    const booting =
      sandboxStatus === 'pending' ||
      sandboxStatus === 'creating' ||
      sandboxStatus === 'unknown'
    return (
      <EmptySplash
        title={booting ? 'Connecting desktop…' : 'Sandbox not running'}
        body={
          booting
            ? 'Waiting for the sandbox to reach running before opening noVNC.'
            : `Desktop needs a running sandbox (status: ${sandboxStatus}).`
        }
      />
    )
  }

  if (error && !iframeSrc) {
    return (
      <EmptySplash
        title="Desktop unavailable"
        body={error}
        primaryLabel="Retry"
        onPrimary={() => void mint()}
      />
    )
  }

  if (!iframeSrc) {
    return (
      <div className="studio-empty-splash" style={{ display: 'grid', placeItems: 'center' }}>
        <Spinner size="lg" aria-label="Connecting desktop" />
        <p style={{ marginTop: '0.75rem', opacity: 0.8 }}>
          {minting ? 'Connecting to desktop…' : 'Preparing desktop…'}
        </p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span style={{ opacity: 0.75, fontSize: '0.85rem' }}>
          noVNC · :{DESKTOP_PORT}
          {fbLabel ? ` · ${fbLabel}` : ''}
        </span>
        <Button
          variant="control"
          aria-label="Refresh desktop"
          onClick={() => {
            setTick((t) => t + 1)
            lastSize.current = null
            void mint()
          }}
          icon={<SyncAltIcon />}
        />
      </div>
      <div
        ref={frameHostRef}
        className="preview-frame preview-frame-full"
        style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}
      >
        <iframe
          key={tick}
          className="preview-iframe"
          title="Sandbox desktop"
          src={iframeSrc}
          allow="clipboard-read; clipboard-write"
          style={{ width: '100%', height: '100%', border: 0, display: 'block' }}
        />
      </div>
    </div>
  )
}
