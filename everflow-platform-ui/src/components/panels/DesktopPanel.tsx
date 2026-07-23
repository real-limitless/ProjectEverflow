import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Spinner } from '@patternfly/react-core'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  createPreviewEndpoint,
  isDemoMode,
  previewIframeSrc,
  type PreviewEndpoint,
} from '@/lib/api'
import { usePlaygroundStore } from '@/store/playgroundStore'

const DESKTOP_PORT = 6080
const VNC_PATH = '/vnc.html'

function desktopIframeSrc(endpoint: PreviewEndpoint): string {
  const base = previewIframeSrc(endpoint, VNC_PATH)
  try {
    const u = new URL(base)
    u.searchParams.set('autoconnect', '1')
    u.searchParams.set('resize', 'scale')
    return u.href
  } catch {
    const join = base.includes('?') ? '&' : '?'
    return `${base}${join}autoconnect=1&resize=scale`
  }
}

/**
 * Live Linux desktop via guest noVNC (port 6080), framed through the preview proxy.
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
  const remintTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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

  useEffect(() => {
    if (!sandboxRunning) {
      setIframeSrc(null)
      setError(null)
      if (remintTimer.current) clearTimeout(remintTimer.current)
      return
    }
    void mint()
    return () => {
      if (remintTimer.current) clearTimeout(remintTimer.current)
    }
  }, [sandboxRunning, mint])

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
        <span style={{ opacity: 0.75, fontSize: '0.85rem' }}>noVNC · :{DESKTOP_PORT}</span>
        <Button
          variant="control"
          aria-label="Refresh desktop"
          onClick={() => {
            setTick((t) => t + 1)
            void mint()
          }}
          icon={<SyncAltIcon />}
        />
      </div>
      <div className="preview-frame preview-frame-full" style={{ flex: 1, minHeight: 0 }}>
        <iframe
          key={tick}
          className="preview-iframe"
          title="Sandbox desktop"
          src={iframeSrc}
          allow="clipboard-read; clipboard-write"
          style={{ width: '100%', height: '100%', border: 0 }}
        />
      </div>
    </div>
  )
}
