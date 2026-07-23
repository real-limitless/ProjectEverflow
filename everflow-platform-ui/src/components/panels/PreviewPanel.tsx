import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import {
  Button,
  EmptyState,
  EmptyStateBody,
  EmptyStateVariant,
  InputGroup,
  InputGroupItem,
  MenuToggle,
  Select,
  SelectList,
  SelectOption,
  Spinner,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import AngleLeftIcon from '@patternfly/react-icons/dist/esm/icons/angle-left-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import CubesIcon from '@patternfly/react-icons/dist/esm/icons/cubes-icon'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import {
  createPreviewEndpoint,
  isDemoMode,
  listSandboxPorts,
  previewIframeSrc,
  type PreviewEndpoint,
  type SandboxListeningPort,
} from '@/lib/api'
import { getPreviewServices } from '@/data/previewServices'
import { getProject } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

type DeviceMode = 'full' | 'desktop' | 'tablet' | 'mobile'
type FramedDevice = Exclude<DeviceMode, 'full'>

type PreviewNavState = { stack: string[]; index: number }

const PREVIEW_NAV_MSG = 'everflow-preview-nav'
const PREVIEW_HISTORY_MSG = 'everflow-preview-history'

const PORT_POLL_MS = 4000

/** Everflow / Desktop internals — never offer as Preview app targets (client guard). */
const PREVIEW_EXCLUDED_PORTS = new Set([
  22, // ssh
  4096, // OpenCode
  5900, // x11vnc
  6080, // noVNC (Desktop panel)
  18765, // Everflow MCP API tunnel
])

/** Responsive preset widths (px). Full mode uses 100% of the panel. */
const PRESET_WIDTH: Record<FramedDevice, number> = {
  desktop: 1280,
  tablet: 768,
  mobile: 390,
}

const VIEWPORT_MIN = 280
const VIEWPORT_PAD = 24 // frame horizontal padding budget for max width

function clampViewportWidth(width: number, frameWidth: number): number {
  const max = Math.max(VIEWPORT_MIN, frameWidth - VIEWPORT_PAD)
  return Math.min(max, Math.max(VIEWPORT_MIN, Math.round(width)))
}

function usePreviewViewport(initial: DeviceMode = 'full') {
  const [device, setDeviceState] = useState<DeviceMode>(initial)
  const [viewportWidth, setViewportWidth] = useState<number>(PRESET_WIDTH.desktop)
  const [resizing, setResizing] = useState(false)
  const frameRef = useRef<HTMLDivElement | null>(null)
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const setDevice = useCallback((next: DeviceMode) => {
    setDeviceState(next)
    if (next === 'full') return
    const frameW = frameRef.current?.clientWidth ?? 1600
    setViewportWidth(clampViewportWidth(PRESET_WIDTH[next], frameW))
  }, [])

  const onResizePointerDown = useCallback(
    (e: PointerEvent<HTMLButtonElement>) => {
      if (device === 'full') return
      e.preventDefault()
      e.currentTarget.setPointerCapture(e.pointerId)
      dragRef.current = { startX: e.clientX, startWidth: viewportWidth }
      setResizing(true)
    },
    [device, viewportWidth],
  )

  const onResizePointerMove = useCallback((e: PointerEvent<HTMLButtonElement>) => {
    if (!dragRef.current) return
    // Drag handle left → increase width; right → decrease
    const delta = dragRef.current.startX - e.clientX
    const frameW = frameRef.current?.clientWidth ?? 1600
    setViewportWidth(clampViewportWidth(dragRef.current.startWidth + delta, frameW))
  }, [])

  const onResizePointerUp = useCallback((e: PointerEvent<HTMLButtonElement>) => {
    if (dragRef.current) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId)
      } catch {
        /* already released */
      }
    }
    dragRef.current = null
    setResizing(false)
  }, [])

  const onResizeKeyDown = useCallback(
    (e: KeyboardEvent<HTMLButtonElement>) => {
      if (device === 'full') return
      const step = e.shiftKey ? 50 : 10
      const frameW = frameRef.current?.clientWidth ?? 1600
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        setViewportWidth((w) => clampViewportWidth(w + step, frameW))
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        setViewportWidth((w) => clampViewportWidth(w - step, frameW))
      }
    },
    [device],
  )

  // Re-clamp when the panel resizes (window / dock)
  useEffect(() => {
    const el = frameRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => {
      if (device === 'full') return
      setViewportWidth((w) => clampViewportWidth(w, el.clientWidth))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [device])

  return {
    device,
    setDevice,
    viewportWidth,
    resizing,
    frameRef,
    onResizePointerDown,
    onResizePointerMove,
    onResizePointerUp,
    onResizePointerCancel: onResizePointerUp,
    onResizeKeyDown,
  }
}

function PreviewDeviceShell({
  device,
  viewportWidth,
  resizing,
  frameRef,
  onResizePointerDown,
  onResizePointerMove,
  onResizePointerUp,
  onResizeKeyDown,
  frameKey,
  children,
}: {
  device: DeviceMode
  viewportWidth: number
  resizing: boolean
  frameRef: RefObject<HTMLDivElement | null>
  onResizePointerDown: (e: PointerEvent<HTMLButtonElement>) => void
  onResizePointerMove: (e: PointerEvent<HTMLButtonElement>) => void
  onResizePointerUp: (e: PointerEvent<HTMLButtonElement>) => void
  onResizeKeyDown: (e: KeyboardEvent<HTMLButtonElement>) => void
  frameKey?: string
  children: ReactNode
}) {
  const isFull = device === 'full'
  return (
    <div
      ref={frameRef}
      className={`panel-scroll preview-frame${isFull ? ' preview-frame-full' : ''}${resizing ? ' is-resizing' : ''}`}
      key={frameKey}
    >
      <div
        className={`preview-device ${device}`}
        style={isFull ? undefined : { width: viewportWidth }}
      >
        {!isFull && (
          <button
            type="button"
            className="preview-resize-handle"
            aria-label="Resize preview width"
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={viewportWidth}
            aria-valuemin={VIEWPORT_MIN}
            tabIndex={0}
            onPointerDown={onResizePointerDown}
            onPointerMove={onResizePointerMove}
            onPointerUp={onResizePointerUp}
            onPointerCancel={onResizePointerUp}
            onKeyDown={onResizeKeyDown}
          />
        )}
        <div className="preview-device-main">{children}</div>
      </div>
    </div>
  )
}

function DeviceModeTabs({
  device,
  onDeviceChange,
  viewportWidth,
}: {
  device: DeviceMode
  onDeviceChange: (d: DeviceMode) => void
  viewportWidth: number
}) {
  return (
    <>
      <Tabs
        activeKey={device}
        onSelect={(_e, k) => onDeviceChange(k as DeviceMode)}
        variant="secondary"
        className="panel-pf-tabs preview-device-tabs"
      >
        <Tab eventKey="full" title={<TabTitleText>Full</TabTitleText>} />
        <Tab eventKey="desktop" title={<TabTitleText>Desktop</TabTitleText>} />
        <Tab eventKey="tablet" title={<TabTitleText>Tablet</TabTitleText>} />
        <Tab eventKey="mobile" title={<TabTitleText>Mobile</TabTitleText>} />
      </Tabs>
      {device !== 'full' && (
        <span className="preview-size-label" title="Viewport width">
          {viewportWidth}px
        </span>
      )}
    </>
  )
}

/** Extract path (+ search/hash) from a full URL for display. */
function urlToPath(fullUrl: string): string {
  try {
    const u = new URL(fullUrl)
    return `${u.pathname || '/'}${u.search}${u.hash}` || '/'
  } catch {
    if (fullUrl.startsWith('/')) return fullUrl || '/'
    return '/'
  }
}

/** Origin of a service URL (protocol + host + port). */
function urlOrigin(fullUrl: string): string {
  try {
    return new URL(fullUrl).origin
  } catch {
    return 'http://localhost:5173'
  }
}

/** Join service origin with a user-entered path. */
function joinOriginAndPath(origin: string, path: string): string {
  const cleaned = path.trim() || '/'
  const withSlash = cleaned.startsWith('/') ? cleaned : `/${cleaned}`
  try {
    return new URL(withSlash, origin.endsWith('/') ? origin : `${origin}/`).href
  } catch {
    return `${origin}${withSlash}`
  }
}

/** Normalize a preview path for the address bar (drop ticket query param). */
function normalizePreviewPath(path: string): string {
  const raw = path.trim() || '/'
  const withSlash = raw.startsWith('/') ? raw : `/${raw}`
  try {
    const u = new URL(withSlash, 'http://preview.local')
    u.searchParams.delete('ticket')
    const q = u.searchParams.toString()
    return `${u.pathname || '/'}${q ? `?${q}` : ''}${u.hash}` || '/'
  } catch {
    return withSlash
  }
}

function pushPreviewNav(prev: PreviewNavState, path: string): PreviewNavState {
  const p = normalizePreviewPath(path)
  if (prev.stack[prev.index] === p) return prev
  const stack = prev.stack.slice(0, prev.index + 1)
  stack.push(p)
  return { stack, index: stack.length - 1 }
}

function resetPreviewNav(path = '/'): PreviewNavState {
  return { stack: [normalizePreviewPath(path)], index: 0 }
}

export function PreviewPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const demo = isDemoMode()

  if (demo) {
    return <DemoPreviewPanel projectId={currentProjectId} />
  }

  return <LivePreviewPanel projectId={currentProjectId} />
}

function LivePreviewPanel({ projectId }: { projectId: string | null }) {
  const {
    device,
    setDevice,
    viewportWidth,
    resizing,
    frameRef,
    onResizePointerDown,
    onResizePointerMove,
    onResizePointerUp,
    onResizeKeyDown,
  } = usePreviewViewport('full')
  const [ports, setPorts] = useState<SandboxListeningPort[]>([])
  const [loadingPorts, setLoadingPorts] = useState(false)
  const [portsError, setPortsError] = useState<string | null>(null)
  const [selectedPort, setSelectedPort] = useState<number | null>(null)
  const [endpoint, setEndpoint] = useState<PreviewEndpoint | null>(null)
  const [iframeSrc, setIframeSrc] = useState<string | null>(null)
  const [pathInput, setPathInput] = useState('/')
  const [nav, setNav] = useState<PreviewNavState>(() => resetPreviewNav('/'))
  const [selectOpen, setSelectOpen] = useState(false)
  const [mintError, setMintError] = useState<string | null>(null)
  const [minting, setMinting] = useState(false)
  const [tick, setTick] = useState(0)
  const remintTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const expectHistoryNav = useRef(false)
  /** True when the current iframe document still has usable session history (SPA / in-frame nav). */
  const iframeHistoryLive = useRef(false)

  const previewOrigin = useMemo(() => {
    if (!endpoint?.url) return null
    try {
      return new URL(endpoint.url).origin
    } catch {
      return null
    }
  }, [endpoint?.url])

  const canGoBack = nav.index > 0
  const canGoForward = nav.index < nav.stack.length - 1

  const pollPorts = useCallback(async () => {
    if (!projectId) {
      setPorts([])
      return
    }
    setLoadingPorts(true)
    try {
      const res = await listSandboxPorts(projectId)
      setPorts(
        (res.ports || []).filter(
          (p) =>
            !PREVIEW_EXCLUDED_PORTS.has(p.port) &&
            !(p.port >= 14100 && p.port < 14200),
        ),
      )
      setPortsError(null)
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to list ports'
      setPortsError(msg)
    } finally {
      setLoadingPorts(false)
    }
  }, [projectId])

  useEffect(() => {
    void pollPorts()
    if (!projectId) return
    const id = setInterval(() => void pollPorts(), PORT_POLL_MS)
    return () => clearInterval(id)
  }, [projectId, pollPorts])

  // Auto-select first http_likely port when available
  useEffect(() => {
    if (selectedPort != null) {
      // Keep selection if still present
      if (ports.some((p) => p.port === selectedPort)) return
    }
    const preferred = ports.find((p) => p.http_likely) || ports[0]
    if (preferred) {
      setSelectedPort(preferred.port)
    } else {
      setSelectedPort(null)
      setEndpoint(null)
      setIframeSrc(null)
    }
  }, [ports, selectedPort])

  const mint = useCallback(
    async (port: number, path = '/') => {
      if (!projectId) return
      setMinting(true)
      setMintError(null)
      try {
        const ep = await createPreviewEndpoint(projectId, port)
        const cleaned = normalizePreviewPath(path)
        setEndpoint(ep)
        setIframeSrc(previewIframeSrc(ep, cleaned))
        setPathInput(cleaned)

        if (remintTimer.current) clearTimeout(remintTimer.current)
        // Remint ~60s before expiry
        const ms = Math.max(30_000, ep.expires_at * 1000 - Date.now() - 60_000)
        remintTimer.current = setTimeout(() => {
          void mint(port, path)
        }, ms)
      } catch (e) {
        setMintError(e instanceof Error ? e.message : 'Failed to open preview')
        setEndpoint(null)
        setIframeSrc(null)
      } finally {
        setMinting(false)
      }
    },
    [projectId],
  )

  useEffect(() => {
    if (selectedPort == null || !projectId) return
    setNav(resetPreviewNav(pathInput || '/'))
    void mint(selectedPort, pathInput || '/')
    return () => {
      if (remintTimer.current) clearTimeout(remintTimer.current)
    }
    // Only remint when port or project changes — not every path keystroke
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPort, projectId])

  const selected = ports.find((p) => p.port === selectedPort) || null

  const selectPort = (port: number) => {
    setSelectedPort(port)
    setSelectOpen(false)
    setPathInput('/')
    setNav(resetPreviewNav('/'))
  }

  const applyPath = (path: string) => {
    const withSlash = normalizePreviewPath(path)
    setPathInput(withSlash)
    setNav((prev) => pushPreviewNav(prev, withSlash))
    // Address-bar loads remount the frame (tick) and clear iframe session history.
    iframeHistoryLive.current = false
    if (endpoint) {
      setIframeSrc(previewIframeSrc(endpoint, withSlash))
      setTick((t) => t + 1)
    } else if (selectedPort != null) {
      void mint(selectedPort, withSlash)
    }
  }

  const goHistory = (delta: -1 | 1) => {
    const next = nav.index + delta
    if (next < 0 || next >= nav.stack.length) return
    const target = nav.stack[next]
    expectHistoryNav.current = true
    setNav((prev) => ({ ...prev, index: next }))
    setPathInput(target)
    if (
      iframeHistoryLive.current &&
      iframeRef.current?.contentWindow &&
      previewOrigin
    ) {
      iframeRef.current.contentWindow.postMessage(
        { type: PREVIEW_HISTORY_MSG, delta },
        previewOrigin,
      )
      return
    }
    // Fallback: parent path stack for address-bar navigations / remounted iframe
    if (endpoint) {
      setIframeSrc(previewIframeSrc(endpoint, target))
      setTick((t) => t + 1)
    }
  }

  useEffect(() => {
    if (!previewOrigin) return
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== previewOrigin) return
      const data = event.data
      if (!data || data.type !== PREVIEW_NAV_MSG || typeof data.path !== 'string') return
      const path = normalizePreviewPath(data.path)
      setPathInput(path)
      if (expectHistoryNav.current) {
        expectHistoryNav.current = false
        setNav((prev) => {
          if (prev.stack[prev.index] === path) return prev
          const stack = [...prev.stack]
          stack[prev.index] = path
          return { ...prev, stack }
        })
        return
      }
      setNav((prev) => {
        // In-frame SPA/hash nav — enable postMessage back/forward.
        // Ignore the bridge's initial report when it matches the stack tip.
        if (prev.stack[prev.index] !== path) {
          iframeHistoryLive.current = true
        }
        return pushPreviewNav(prev, path)
      })
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [previewOrigin])

  const refresh = () => {
    if (selectedPort != null) {
      void mint(selectedPort, pathInput || '/')
    } else {
      void pollPorts()
    }
    setTick((t) => t + 1)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar preview-toolbar">
        <div className="preview-service-bar">
          <Select
            isOpen={selectOpen}
            selected={selectedPort != null ? String(selectedPort) : ''}
            onSelect={(_e, value) => selectPort(Number(value))}
            onOpenChange={setSelectOpen}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                onClick={() => setSelectOpen(!selectOpen)}
                isExpanded={selectOpen}
                className="preview-service-toggle"
              >
                {selected?.label || (loadingPorts ? 'Scanning…' : 'No services')}
              </MenuToggle>
            )}
          >
            <SelectList>
              {ports.length === 0 && (
                <SelectOption isDisabled value="">
                  {portsError || 'No listening ports yet'}
                </SelectOption>
              )}
              {ports.map((p) => (
                <SelectOption
                  key={p.port}
                  value={String(p.port)}
                  description={`${p.address}:${p.port}${p.http_likely ? ' · http' : ''}`}
                >
                  {p.label || `:${p.port}`}
                </SelectOption>
              ))}
            </SelectList>
          </Select>
          <DeviceModeTabs
            device={device}
            onDeviceChange={setDevice}
            viewportWidth={viewportWidth}
          />
          <InputGroup className="preview-address-group">
            <InputGroupItem>
              <Button
                variant="control"
                className="preview-nav-btn"
                aria-label="Back"
                isDisabled={!selectedPort || !canGoBack}
                onClick={() => goHistory(-1)}
                icon={<AngleLeftIcon />}
              />
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                className="preview-nav-btn"
                aria-label="Forward"
                isDisabled={!selectedPort || !canGoForward}
                onClick={() => goHistory(1)}
                icon={<AngleRightIcon />}
              />
            </InputGroupItem>
            <InputGroupItem isFill>
              <TextInput
                value={pathInput}
                onChange={(_e, v) => setPathInput(v)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applyPath(pathInput)
                }}
                onBlur={() => applyPath(pathInput)}
                aria-label="Preview path"
                placeholder="/"
                isDisabled={!selectedPort}
              />
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                aria-label="Refresh preview"
                onClick={refresh}
                icon={<SyncAltIcon />}
              />
            </InputGroupItem>
          </InputGroup>
        </div>
      </div>
      <PreviewDeviceShell
        device={device}
        viewportWidth={viewportWidth}
        resizing={resizing}
        frameRef={frameRef}
        onResizePointerDown={onResizePointerDown}
        onResizePointerMove={onResizePointerMove}
        onResizePointerUp={onResizePointerUp}
        onResizeKeyDown={onResizeKeyDown}
        frameKey={`${selectedPort}-${tick}`}
      >
        <div className="preview-body preview-body-live">
          {!projectId && (
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="No project open"
              headingLevel="h4"
              icon={CubesIcon}
            >
              <EmptyStateBody>
                Open a project with a running sandbox to preview apps.
              </EmptyStateBody>
            </EmptyState>
          )}
          {projectId && !selectedPort && !loadingPorts && (
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="Waiting for a web server"
              headingLevel="h4"
              icon={CubesIcon}
            >
              <EmptyStateBody>
                {portsError
                  ? portsError
                  : 'Start a server in the Terminal or chat (for example npm run dev). Listening ports appear here automatically.'}
              </EmptyStateBody>
            </EmptyState>
          )}
          {projectId && selectedPort && minting && !iframeSrc && (
            <div className="preview-hero">
              <Spinner size="lg" />
              <p>Opening preview on port {selectedPort}…</p>
            </div>
          )}
          {mintError && (
            <EmptyState
              variant={EmptyStateVariant.sm}
              titleText="Preview error"
              headingLevel="h4"
            >
              <EmptyStateBody>{mintError}</EmptyStateBody>
            </EmptyState>
          )}
          {iframeSrc && (
            <iframe
              ref={iframeRef}
              title="Sandbox preview"
              src={iframeSrc}
              className="preview-iframe"
              // No sandbox attribute: sandboxed iframes break Vite HMR WebSockets
              // and many app APIs. Preview content is already isolated by origin
              // ({uuid}.preview.localhost) and capability auth.
              allow="clipboard-read; clipboard-write; fullscreen; autoplay"
              referrerPolicy="strict-origin-when-cross-origin"
            />
          )}
        </div>
      </PreviewDeviceShell>
    </div>
  )
}

function DemoPreviewPanel({ projectId }: { projectId: string | null }) {
  const p = getProject(projectId)
  const services = useMemo(() => getPreviewServices(projectId), [projectId])
  const {
    device,
    setDevice,
    viewportWidth,
    resizing,
    frameRef,
    onResizePointerDown,
    onResizePointerMove,
    onResizePointerUp,
    onResizeKeyDown,
  } = usePreviewViewport('full')
  const [serviceId, setServiceId] = useState(services[0]?.id || 'web')
  const [url, setUrl] = useState(services[0]?.url || 'http://localhost:5173')
  const [pathInput, setPathInput] = useState(() =>
    urlToPath(services[0]?.url || 'http://localhost:5173'),
  )
  const [nav, setNav] = useState<PreviewNavState>(() =>
    resetPreviewNav(urlToPath(services[0]?.url || 'http://localhost:5173')),
  )
  const [selectOpen, setSelectOpen] = useState(false)
  const [tick, setTick] = useState(0)

  const canGoBack = nav.index > 0
  const canGoForward = nav.index < nav.stack.length - 1

  useEffect(() => {
    const list = getPreviewServices(projectId)
    const first = list[0]
    const nextUrl = first?.url || 'http://localhost:5173'
    const nextPath = urlToPath(nextUrl)
    setServiceId(first?.id || 'web')
    setUrl(nextUrl)
    setPathInput(nextPath)
    setNav(resetPreviewNav(nextPath))
  }, [projectId])

  const service = services.find((s) => s.id === serviceId) || services[0]
  const origin = urlOrigin(service?.url || url)

  const selectService = (id: string) => {
    const s = services.find((x) => x.id === id)
    if (!s) return
    const nextPath = urlToPath(s.url)
    setServiceId(id)
    setUrl(s.url)
    setPathInput(nextPath)
    setNav(resetPreviewNav(nextPath))
    setSelectOpen(false)
  }

  const applyPath = (path: string, opts?: { record?: boolean }) => {
    const next = joinOriginAndPath(origin, path)
    const nextPath = urlToPath(next)
    setUrl(next)
    setPathInput(nextPath)
    if (opts?.record !== false) {
      setNav((prev) => pushPreviewNav(prev, nextPath))
    }
    setTick((t) => t + 1)
  }

  const goHistory = (delta: -1 | 1) => {
    const next = nav.index + delta
    if (next < 0 || next >= nav.stack.length) return
    const target = nav.stack[next]
    setNav((prev) => ({ ...prev, index: next }))
    applyPath(target, { record: false })
  }

  const refresh = () => {
    applyPath(pathInput, { record: false })
  }

  const displayPath = urlToPath(url)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar preview-toolbar">
        <div className="preview-service-bar">
          <Select
            isOpen={selectOpen}
            selected={serviceId}
            onSelect={(_e, value) => selectService(String(value))}
            onOpenChange={setSelectOpen}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                onClick={() => setSelectOpen(!selectOpen)}
                isExpanded={selectOpen}
                className="preview-service-toggle"
              >
                {service?.label || 'Service'}
              </MenuToggle>
            )}
          >
            <SelectList>
              {services.map((s) => (
                <SelectOption key={s.id} value={s.id} description={urlToPath(s.url)}>
                  {s.label}
                </SelectOption>
              ))}
            </SelectList>
          </Select>
          <DeviceModeTabs
            device={device}
            onDeviceChange={setDevice}
            viewportWidth={viewportWidth}
          />
          <InputGroup className="preview-address-group">
            <InputGroupItem>
              <Button
                variant="control"
                className="preview-nav-btn"
                aria-label="Back"
                isDisabled={!canGoBack}
                onClick={() => goHistory(-1)}
                icon={<AngleLeftIcon />}
              />
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                className="preview-nav-btn"
                aria-label="Forward"
                isDisabled={!canGoForward}
                onClick={() => goHistory(1)}
                icon={<AngleRightIcon />}
              />
            </InputGroupItem>
            <InputGroupItem isFill>
              <TextInput
                value={pathInput}
                onChange={(_e, v) => setPathInput(v)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applyPath(pathInput)
                }}
                onBlur={() => {
                  setPathInput(urlToPath(joinOriginAndPath(origin, pathInput)))
                }}
                aria-label="Preview path"
                placeholder="/"
              />
            </InputGroupItem>
            <InputGroupItem>
              <Button
                variant="control"
                aria-label="Refresh preview"
                onClick={refresh}
                icon={<SyncAltIcon />}
              />
            </InputGroupItem>
          </InputGroup>
        </div>
      </div>
      <PreviewDeviceShell
        device={device}
        viewportWidth={viewportWidth}
        resizing={resizing}
        frameRef={frameRef}
        onResizePointerDown={onResizePointerDown}
        onResizePointerMove={onResizePointerMove}
        onResizePointerUp={onResizePointerUp}
        onResizeKeyDown={onResizeKeyDown}
        frameKey={`${serviceId}-${tick}-${url}`}
      >
        <div className="preview-body">
          <PreviewDemoBody
            kind={service?.kind || 'frontend'}
            label={service?.label || 'Service'}
            projectName={p?.name || 'App'}
            path={displayPath}
          />
        </div>
      </PreviewDeviceShell>
    </div>
  )
}

function PreviewDemoBody({
  kind,
  label,
  projectName,
  path,
}: {
  kind: string
  label: string
  projectName: string
  path: string
}) {
  if (kind === 'backend') {
    return (
      <div className="preview-hero">
        <h1>{label}</h1>
        <p>
          API surface for <strong>{projectName}</strong> · demo OpenAPI placeholder
        </p>
        <pre className="preview-code-block">{`GET ${path === '/' ? '' : path}/health → 200 OK
GET ${path === '/' ? '' : path}/v1/metrics → { cpu: 42, mem: 67 }
POST ${path === '/' ? '' : path}/v1/deploy → 202 Accepted`}</pre>
      </div>
    )
  }
  if (kind === 'admin') {
    return (
      <div className="preview-hero">
        <h1>{label}</h1>
        <p>Admin console mock · users, policies, audit</p>
        <div className="preview-metrics">
          <div className="metric ok">
            <span className="m-val">12</span>
            <span className="m-lab">Users</span>
          </div>
          <div className="metric warn">
            <span className="m-val">3</span>
            <span className="m-lab">Pending</span>
          </div>
          <div className="metric ok">
            <span className="m-val">OK</span>
            <span className="m-lab">SSO</span>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="preview-hero">
      <h1>{projectName}</h1>
      <p>
        {label} preview · <code>{path}</code>
      </p>
      <div className="preview-metrics">
        <div className="metric ok">
          <span className="m-val">42%</span>
          <span className="m-lab">CPU</span>
        </div>
        <div className="metric warn">
          <span className="m-val">67%</span>
          <span className="m-lab">Memory</span>
        </div>
        <div className="metric ok">
          <span className="m-val">12</span>
          <span className="m-lab">Containers</span>
        </div>
      </div>
    </div>
  )
}
