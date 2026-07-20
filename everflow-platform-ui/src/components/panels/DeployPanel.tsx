import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  Tabs,
  Tab,
  TabTitleText,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import {
  DEPLOY_ENVS,
  composeSnippet,
  defaultComposeForEnv,
} from '@/components/panels/deploy/composeSnippets'
import { runDeploySimulation } from '@/lib/deploySimulation'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import { StatusLabel } from './statusLabel'
import type {
  DeployAction,
  DeployPipelineStage,
  DeployRun,
  DeployRunStatus,
} from '@/types/studio'

function uid(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function hostLabel(h: { user?: string; host: string; port?: number }) {
  const user = h.user ?? 'everflow'
  const port = h.port ?? 22
  return `${user}@${h.host}${port !== 22 ? `:${port}` : ''}`
}

export function DeployPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const state = useProjectStudio(projectId)
  const addHost = useStudioDemoStore((s) => s.addHost)
  const removeHost = useStudioDemoStore((s) => s.removeHost)
  const saveDeployRun = useStudioDemoStore((s) => s.saveDeployRun)
  const finalizeDeployRun = useStudioDemoStore((s) => s.finalizeDeployRun)

  const hosts = state.deployHosts
  const composeFiles = state.composeFiles
  const envEntries = state.envEntries
  const deployRuns = state.deployRuns ?? []
  const deployServices = state.deployServices ?? []
  const deploys = state.deploys

  const [hostId, setHostId] = useState(hosts[0]?.id ?? '')
  const [env, setEnv] = useState<string>('Preview')
  const [composeFile, setComposeFile] = useState(
    defaultComposeForEnv('Preview', composeFiles),
  )
  const [attachedIds, setAttachedIds] = useState<string[]>(() =>
    envEntries.filter((e) => e.kind === 'secret' || e.key.includes('API')).map((e) => e.id).slice(0, 2),
  )
  const [ctxTab, setCtxTab] = useState<'services' | 'env' | 'history' | 'compose'>('services')

  const [stages, setStages] = useState<DeployPipelineStage[]>([])
  const [logLines, setLogLines] = useState<string[]>([
    'Ready. Select a host and run Deploy, Validate, Redeploy, or Stop.',
    'Demo only — no real SSH or podman-compose execution.',
  ])
  const [runStatus, setRunStatus] = useState<DeployRunStatus | 'idle'>('idle')
  const [running, setRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const [hostOpen, setHostOpen] = useState(false)
  const [hostName, setHostName] = useState('')
  const [hostAddr, setHostAddr] = useState('')
  const [hostUser, setHostUser] = useState('everflow')
  const [hostPort, setHostPort] = useState('22')
  const [hostTags, setHostTags] = useState('')

  const selectedHost = hosts.find((h) => h.id === hostId) ?? hosts[0]

  useEffect(() => {
    if (selectedHost && selectedHost.id !== hostId) setHostId(selectedHost.id)
  }, [hosts, selectedHost, hostId])

  useEffect(() => {
    setComposeFile((prev) =>
      composeFiles.includes(prev) ? prev : defaultComposeForEnv(env, composeFiles),
    )
  }, [env, composeFiles])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines])

  const servicesForView = useMemo(
    () =>
      deployServices.filter(
        (s) =>
          (!selectedHost || s.hostId === selectedHost.id) &&
          (s.env === env || !env),
      ),
    [deployServices, selectedHost, env],
  )

  const historyFiltered = deployRuns

  const startRun = async (action: DeployAction) => {
    if (!selectedHost) {
      pushToast('Select a remote host', { kind: 'warning' })
      return
    }
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    const runId = uid('run')
    setActiveRunId(runId)
    setRunning(true)
    setRunStatus('running')
    setCtxTab(action === 'validate' ? 'compose' : 'services')

    const attached = envEntries.filter((e) => attachedIds.includes(e.id))
    const startedAt = new Date().toLocaleTimeString()
    let current: DeployRun = {
      id: runId,
      hostId: selectedHost.id,
      env,
      composeFile,
      action,
      status: 'running',
      startedAt,
      stages: [],
      logLines: [],
      attachedEnvIds: attachedIds,
    }
    saveDeployRun(projectId, current)

    try {
      const result = await runDeploySimulation(
        {
          host: selectedHost,
          composeFile,
          env,
          action,
          attached,
        },
        (u) => {
          setStages(u.stages)
          setLogLines(u.logLines)
          setRunStatus(u.status)
          current = {
            ...current,
            stages: u.stages,
            logLines: u.logLines,
            status: u.status,
          }
          saveDeployRun(projectId, current)
        },
        ac.signal,
      )

      const finished: DeployRun = {
        ...current,
        status: result.status,
        stages: result.stages,
        logLines: result.logLines,
        finishedAt: new Date().toLocaleTimeString(),
        durationLabel: '~' + Math.max(3, Math.round(result.logLines.length * 0.15)) + 's',
      }
      finalizeDeployRun(projectId, finished, {
        url: result.url,
        services: result.services,
      })
      setRunStatus(result.status)
      if (result.status === 'ok') {
        pushToast(
          action === 'down'
            ? 'Stack stopped'
            : action === 'validate'
              ? 'Compose valid'
              : 'Deploy complete',
          {
            description: result.url ?? `${action} on ${selectedHost.name} (demo)`,
            kind: 'success',
          },
        )
        if (result.services.length) setCtxTab('services')
      } else if (result.status === 'err') {
        pushToast('Pipeline failed', { description: 'See log for details (demo)', kind: 'danger' })
      } else if (result.status === 'cancelled') {
        pushToast('Pipeline cancelled', { kind: 'warning' })
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        const cancelled: DeployRun = {
          ...current,
          status: 'cancelled',
          finishedAt: new Date().toLocaleTimeString(),
          logLines: [...current.logLines, 'cancelled by user'],
        }
        finalizeDeployRun(projectId, cancelled, { services: [] })
        setRunStatus('cancelled')
        setLogLines(cancelled.logLines)
        pushToast('Pipeline cancelled', { kind: 'warning' })
      }
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }

  const loadRun = (run: DeployRun) => {
    setActiveRunId(run.id)
    setStages(run.stages)
    setLogLines(run.logLines)
    setRunStatus(run.status)
    setEnv(run.env)
    setComposeFile(run.composeFile)
    if (run.hostId) setHostId(run.hostId)
    setAttachedIds(run.attachedEnvIds)
    setCtxTab('history')
  }

  const toggleAttach = (id: string) => {
    setAttachedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <div>
          <span className="section-label" style={{ margin: 0 }}>
            Remote deploy
          </span>
          <div className="lc-meta" style={{ marginTop: 2 }}>
            podman-compose on another host · demo pipeline (no live SSH)
          </div>
        </div>
        <div className="deploy-actions">
          {running && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => abortRef.current?.abort()}
            >
              Cancel
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            isDisabled={running || !selectedHost}
            onClick={() => startRun('validate')}
          >
            Validate
          </Button>
          <Button
            variant="secondary"
            size="sm"
            isDisabled={running || !selectedHost}
            onClick={() => startRun('down')}
          >
            Stop
          </Button>
          <Button
            variant="secondary"
            size="sm"
            isDisabled={running || !selectedHost}
            onClick={() => startRun('redeploy')}
          >
            Redeploy
          </Button>
          <Button
            variant="primary"
            size="sm"
            isLoading={running}
            isDisabled={running || !selectedHost}
            onClick={() => startRun('up')}
          >
            Deploy
          </Button>
        </div>
      </div>

      {hosts.length === 0 ? (
        <EmptySplash
          title="No remote hosts"
          body="Add a host where Everflow can run podman-compose (demo)."
          primaryLabel="Add host"
          onPrimary={() => setHostOpen(true)}
        />
      ) : (
        <div className="deploy-workbench">
          {/* LEFT */}
          <aside className="deploy-sidebar">
            <div className="deploy-sidebar-scroll">
              <div className="section-label" style={{ marginTop: 0 }}>
                Environment
              </div>
              <div className="deploy-env-chips">
                {DEPLOY_ENVS.map((e) => (
                  <Button
                    key={e}
                    size="sm"
                    variant={env === e ? 'primary' : 'secondary'}
                    onClick={() => {
                      setEnv(e)
                      setComposeFile(defaultComposeForEnv(e, composeFiles))
                    }}
                  >
                    {e}
                  </Button>
                ))}
              </div>

              <div className="section-label">
                Hosts
                <Button
                  variant="link"
                  size="sm"
                  style={{ float: 'right', padding: 0 }}
                  onClick={() => setHostOpen(true)}
                >
                  + Add
                </Button>
              </div>
              {hosts.map((h) => (
                <div
                  key={h.id}
                  className={`deploy-host-card ${selectedHost?.id === h.id ? 'is-selected' : ''}`}
                  onClick={() => setHostId(h.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(ev) => {
                    if (ev.key === 'Enter') setHostId(h.id)
                  }}
                >
                  <div className="lc-row">
                    <strong>{h.name}</strong>
                    <StatusLabel
                      status={
                        h.status === 'online' ? 'ok' : h.status === 'offline' ? 'err' : 'idle'
                      }
                      text={h.status}
                    />
                  </div>
                  <div className="host-addr">{hostLabel(h)}</div>
                  <div style={{ marginTop: 4 }}>
                    {(h.tags ?? []).map((t) => (
                      <span key={t} className="deploy-tag">
                        {t}
                      </span>
                    ))}
                    <span className="deploy-tag">{h.orchestrator ?? 'podman-compose'}</span>
                  </div>
                  {h.status === 'online' && (
                    <>
                      <div className="lc-meta" style={{ marginTop: 4 }}>
                        CPU {h.cpuPct ?? 0}%
                      </div>
                      <div className="deploy-metric">
                        <span style={{ width: `${h.cpuPct ?? 0}%` }} />
                      </div>
                      <div className="lc-meta" style={{ marginTop: 4 }}>
                        Mem {h.memPct ?? 0}%
                      </div>
                      <div className="deploy-metric">
                        <span style={{ width: `${h.memPct ?? 0}%` }} />
                      </div>
                    </>
                  )}
                  <div className="lc-meta" style={{ marginTop: 4 }}>
                    last seen {h.lastSeen ?? '—'}
                  </div>
                  <Button
                    variant="link"
                    isDanger
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      removeHost(projectId, h.id)
                      if (hostId === h.id) setHostId('')
                      pushToast('Host removed', { kind: 'warning' })
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ))}

              <div className="section-label">Live environments</div>
              {deploys.map((d) => (
                <div className="deploy-svc-row" key={d.id}>
                  <div className="lc-row">
                    <strong>{d.env}</strong>
                    <StatusLabel status={d.status} />
                  </div>
                  <div className="lc-meta" style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>
                    {d.url}
                  </div>
                  <div className="lc-meta">
                    {d.composeFile} · {d.when}
                  </div>
                </div>
              ))}
            </div>
          </aside>

          {/* CENTER */}
          <section className="deploy-main">
            <div className="deploy-config-bar">
              <div className="cfg-field">
                <label htmlFor="dep-compose">Compose file</label>
                <FormSelect
                  id="dep-compose"
                  value={composeFile}
                  onChange={(_e, v) => setComposeFile(v)}
                  isDisabled={running}
                >
                  {composeFiles.map((f) => (
                    <FormSelectOption key={f} value={f} label={f} />
                  ))}
                </FormSelect>
              </div>
              <div className="cfg-field">
                <label>Target</label>
                <div className="lc-meta" style={{ fontFamily: 'var(--mono)', paddingBlock: 6 }}>
                  {selectedHost
                    ? `${selectedHost.name} · ${env} · ${attachedIds.length} env attach`
                    : '—'}
                </div>
              </div>
            </div>

            {stages.length > 0 && (
              <div className="deploy-pipeline" aria-label="Pipeline stages">
                {stages.map((s) => (
                  <div
                    key={s.id}
                    className={`deploy-stage ${
                      s.status === 'ok'
                        ? 'is-ok'
                        : s.status === 'running'
                          ? 'is-running'
                          : s.status === 'err'
                            ? 'is-err'
                            : s.status === 'skipped'
                              ? 'is-skipped'
                              : ''
                    }`}
                  >
                    <strong>{s.name}</strong>
                    <div className="lc-meta">{s.status}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="deploy-log-toolbar">
              <span className="section-label" style={{ margin: 0 }}>
                Pipeline log
                {runStatus !== 'idle' && (
                  <Label
                    isCompact
                    color={
                      runStatus === 'ok'
                        ? 'green'
                        : runStatus === 'err'
                          ? 'red'
                          : runStatus === 'running'
                            ? 'blue'
                            : 'orange'
                    }
                    style={{ marginInlineStart: 8 }}
                  >
                    {runStatus}
                  </Label>
                )}
              </span>
              <div style={{ display: 'flex', gap: 4 }}>
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => {
                    void navigator.clipboard?.writeText(logLines.join('\n'))
                    pushToast('Log copied', { kind: 'info' })
                  }}
                >
                  Copy
                </Button>
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => {
                    setLogLines(['Log cleared.'])
                    setStages([])
                    setRunStatus('idle')
                  }}
                  isDisabled={running}
                >
                  Clear
                </Button>
              </div>
            </div>
            <div className="deploy-log" ref={logRef} role="log" aria-live="polite">
              {logLines.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.includes('ERROR')
                      ? 'log-err'
                      : line.includes('complete') || line.includes('passed')
                        ? 'log-ok'
                        : undefined
                  }
                >
                  {line}
                </div>
              ))}
            </div>
          </section>

          {/* RIGHT */}
          <aside className="deploy-inspector">
            <Tabs
              activeKey={ctxTab}
              onSelect={(_e, k) => setCtxTab(k as typeof ctxTab)}
              variant="secondary"
              className="panel-pf-tabs"
            >
              <Tab eventKey="services" title={<TabTitleText>Services</TabTitleText>} />
              <Tab eventKey="env" title={<TabTitleText>Env</TabTitleText>} />
              <Tab eventKey="history" title={<TabTitleText>History</TabTitleText>} />
              <Tab eventKey="compose" title={<TabTitleText>Compose</TabTitleText>} />
            </Tabs>
            <div className="deploy-inspector-body">
              {ctxTab === 'services' && (
                <>
                  {servicesForView.length === 0 ? (
                    <p className="lc-meta">
                      No services for {env} on this host yet. Run Deploy to simulate a stack.
                    </p>
                  ) : (
                    servicesForView.map((svc) => (
                      <div className="deploy-svc-row" key={svc.id}>
                        <div className="lc-row">
                          <strong style={{ fontFamily: 'var(--mono)' }}>{svc.name}</strong>
                          <StatusLabel
                            status={svc.status === 'running' ? 'ok' : svc.status === 'restarting' ? 'run' : 'idle'}
                            text={svc.status}
                          />
                        </div>
                        <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                          {svc.image}
                        </div>
                        <div className="lc-meta">ports {svc.ports}</div>
                      </div>
                    ))
                  )}
                </>
              )}

              {ctxTab === 'env' && (
                <>
                  <p className="lc-meta" style={{ marginTop: 0 }}>
                    Attach project env / secrets for injection during Deploy (values stay masked in
                    logs for secrets).
                  </p>
                  {envEntries.map((e) => (
                    <div className="deploy-env-row" key={e.id}>
                      <Checkbox
                        id={`att-${e.id}`}
                        label={
                          <span>
                            <code style={{ fontFamily: 'var(--mono)' }}>{e.key}</code>{' '}
                            <Label isCompact color={e.kind === 'secret' ? 'orange' : 'blue'}>
                              {e.kind}
                            </Label>
                          </span>
                        }
                        isChecked={attachedIds.includes(e.id)}
                        onChange={() => toggleAttach(e.id)}
                        isDisabled={running}
                      />
                      {e.attachedTo && e.attachedTo.length > 0 && (
                        <div className="lc-meta">tags: {e.attachedTo.join(', ')}</div>
                      )}
                    </div>
                  ))}
                </>
              )}

              {ctxTab === 'history' && (
                <>
                  {historyFiltered.length === 0 ? (
                    <p className="lc-meta">No runs yet.</p>
                  ) : (
                    historyFiltered.map((r) => (
                      <div
                        key={r.id}
                        className={`deploy-hist-row ${activeRunId === r.id ? 'is-selected' : ''}`}
                        onClick={() => loadRun(r)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(ev) => {
                          if (ev.key === 'Enter') loadRun(r)
                        }}
                      >
                        <div className="lc-row">
                          <strong>
                            {r.action} · {r.env}
                          </strong>
                          <StatusLabel status={r.status === 'ok' ? 'ok' : r.status === 'err' ? 'err' : r.status === 'running' ? 'run' : 'idle'} text={r.status} />
                        </div>
                        <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                          {r.composeFile}
                        </div>
                        <div className="lc-meta">
                          {r.startedAt}
                          {r.durationLabel ? ` · ${r.durationLabel}` : ''}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}

              {ctxTab === 'compose' && (
                <pre className="deploy-compose-pre">{composeSnippet(composeFile)}</pre>
              )}
            </div>
          </aside>
        </div>
      )}

      <CreateResourceModal
        isOpen={hostOpen}
        title="Add remote host"
        onClose={() => setHostOpen(false)}
        onSubmit={() => {
          if (!hostName.trim() || !hostAddr.trim()) return
          const tags = hostTags
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean)
          addHost(projectId, {
            name: hostName.trim(),
            host: hostAddr.trim(),
            user: hostUser.trim() || 'everflow',
            port: Number(hostPort) || 22,
            tags,
            orchestrator: 'podman-compose',
          })
          pushToast('Host added', { kind: 'success' })
          setHostName('')
          setHostAddr('')
          setHostUser('everflow')
          setHostPort('22')
          setHostTags('')
          setHostOpen(false)
        }}
        isSubmitDisabled={!hostName.trim() || !hostAddr.trim()}
      >
        <FormGroup label="Display name" isRequired fieldId="dh-name">
          <TextInput id="dh-name" value={hostName} onChange={(_e, v) => setHostName(v)} />
        </FormGroup>
        <FormGroup label="Hostname / IP" isRequired fieldId="dh-host">
          <TextInput
            id="dh-host"
            value={hostAddr}
            onChange={(_e, v) => setHostAddr(v)}
            placeholder="edge-02.internal"
          />
        </FormGroup>
        <FormGroup label="SSH user" fieldId="dh-user">
          <TextInput id="dh-user" value={hostUser} onChange={(_e, v) => setHostUser(v)} />
        </FormGroup>
        <FormGroup label="Port" fieldId="dh-port">
          <TextInput id="dh-port" value={hostPort} onChange={(_e, v) => setHostPort(v)} />
        </FormGroup>
        <FormGroup label="Tags (comma-separated)" fieldId="dh-tags">
          <TextInput
            id="dh-tags"
            value={hostTags}
            onChange={(_e, v) => setHostTags(v)}
            placeholder="edge, gpu"
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
