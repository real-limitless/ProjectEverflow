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
import { PROJECTS } from '@/data/projects'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function PreviewPanel() {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const p = PROJECTS[currentProjectId]
  const services = useMemo(
    () => getPreviewServices(currentProjectId),
    [currentProjectId],
  )
  const [device, setDevice] = useState<'desktop' | 'tablet' | 'mobile'>('desktop')
  const [serviceId, setServiceId] = useState(services[0]?.id || 'web')
  const [url, setUrl] = useState(services[0]?.url || 'http://localhost:5173')
  const [selectOpen, setSelectOpen] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const list = getPreviewServices(currentProjectId)
    const first = list[0]
    setServiceId(first?.id || 'web')
    setUrl(first?.url || 'http://localhost:5173')
  }, [currentProjectId])

  const service = services.find((s) => s.id === serviceId) || services[0]

  const selectService = (id: string) => {
    const s = services.find((x) => x.id === id)
    if (!s) return
    setServiceId(id)
    setUrl(s.url)
    setSelectOpen(false)
  }

  const refresh = () => setTick((t) => t + 1)

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
                <SelectOption key={s.id} value={s.id} description={s.url}>
                  {s.label}
                </SelectOption>
              ))}
            </SelectList>
          </Select>
          <InputGroup className="preview-address-group">
            <InputGroupItem isFill>
              <TextInput
                value={url}
                onChange={(_e, v) => setUrl(v)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') refresh()
                }}
                aria-label="Preview address"
                placeholder="http://localhost:port"
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
        <Tabs
          activeKey={device}
          onSelect={(_e, k) => setDevice(k as typeof device)}
          variant="secondary"
          className="panel-pf-tabs"
        >
          <Tab eventKey="desktop" title={<TabTitleText>Desktop</TabTitleText>} />
          <Tab eventKey="tablet" title={<TabTitleText>Tablet</TabTitleText>} />
          <Tab eventKey="mobile" title={<TabTitleText>Mobile</TabTitleText>} />
        </Tabs>
      </div>
      <div className="panel-scroll preview-frame" key={`${serviceId}-${tick}-${url}`}>
        <div className={`preview-device ${device}`}>
          <div className="preview-chrome">
            <span className="dot r" />
            <span className="dot y" />
            <span className="dot g" />
            <span className="url">{url}</span>
          </div>
          <div className="preview-body">
            <PreviewDemoBody
              kind={service?.kind || 'frontend'}
              label={service?.label || 'Service'}
              projectName={p?.name || 'App'}
              url={url}
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
  url,
}: {
  kind: string
  label: string
  projectName: string
  url: string
}) {
  if (kind === 'backend') {
    return (
      <div className="preview-hero">
        <h1>{label}</h1>
        <p>
          API surface for <strong>{projectName}</strong> · demo OpenAPI placeholder
        </p>
        <pre className="preview-code-block">{`GET ${url}/health → 200 OK
GET ${url}/v1/metrics → { cpu: 42, mem: 67 }
POST ${url}/v1/deploy → 202 Accepted`}</pre>
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
        {label} preview · <code>{url}</code>
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
