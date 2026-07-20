import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  InputGroup,
  InputGroupItem,
  MenuToggle,
  Select,
  SelectList,
  SelectOption,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import { getPreviewServices } from '@/data/previewServices'
import { getProject } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

type DeviceMode = 'full' | 'desktop' | 'tablet' | 'mobile'

/** Extract path (+ search/hash) from a full URL for display. */
function urlToPath(fullUrl: string): string {
  try {
    const u = new URL(fullUrl)
    return `${u.pathname || '/'}${u.search}${u.hash}` || '/'
  } catch {
    // Already a path, or malformed — treat as path-like
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

export function PreviewPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = getProject(currentProjectId)
  const services = useMemo(
    () => getPreviewServices(currentProjectId),
    [currentProjectId],
  )
  const [device, setDevice] = useState<DeviceMode>('full')
  const [serviceId, setServiceId] = useState(services[0]?.id || 'web')
  const [url, setUrl] = useState(services[0]?.url || 'http://localhost:5173')
  const [pathInput, setPathInput] = useState(() =>
    urlToPath(services[0]?.url || 'http://localhost:5173'),
  )
  const [selectOpen, setSelectOpen] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const list = getPreviewServices(currentProjectId)
    const first = list[0]
    const nextUrl = first?.url || 'http://localhost:5173'
    setServiceId(first?.id || 'web')
    setUrl(nextUrl)
    setPathInput(urlToPath(nextUrl))
  }, [currentProjectId])

  const service = services.find((s) => s.id === serviceId) || services[0]
  const origin = urlOrigin(service?.url || url)

  const selectService = (id: string) => {
    const s = services.find((x) => x.id === id)
    if (!s) return
    setServiceId(id)
    setUrl(s.url)
    setPathInput(urlToPath(s.url))
    setSelectOpen(false)
  }

  const applyPath = (path: string) => {
    const next = joinOriginAndPath(origin, path)
    setUrl(next)
    setPathInput(urlToPath(next))
    setTick((t) => t + 1)
  }

  const refresh = () => {
    // Re-apply path from the field so edits take effect on refresh
    applyPath(pathInput)
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
          <Tabs
            activeKey={device}
            onSelect={(_e, k) => setDevice(k as DeviceMode)}
            variant="secondary"
            className="panel-pf-tabs preview-device-tabs"
          >
            <Tab eventKey="full" title={<TabTitleText>Full</TabTitleText>} />
            <Tab eventKey="desktop" title={<TabTitleText>Desktop</TabTitleText>} />
            <Tab eventKey="tablet" title={<TabTitleText>Tablet</TabTitleText>} />
            <Tab eventKey="mobile" title={<TabTitleText>Mobile</TabTitleText>} />
          </Tabs>
          <InputGroup className="preview-address-group">
            <InputGroupItem isFill>
              <TextInput
                value={pathInput}
                onChange={(_e, v) => setPathInput(v)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applyPath(pathInput)
                }}
                onBlur={() => {
                  // Normalize display after leaving the field
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
      <div
        className={`panel-scroll preview-frame${device === 'full' ? ' preview-frame-full' : ''}`}
        key={`${serviceId}-${tick}-${url}`}
      >
        <div className={`preview-device ${device}`}>
          <div className="preview-body">
            <PreviewDemoBody
              kind={service?.kind || 'frontend'}
              label={service?.label || 'Service'}
              projectName={p?.name || 'App'}
              path={displayPath}
            />
          </div>
        </div>
      </div>
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
