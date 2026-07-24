import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import {
  DEPLOY_ENVS,
  composeSnippet,
  defaultComposeForEnv,
} from '@/components/panels/deploy/composeSnippets'
import { getProject } from '@/data/projects'
import { isDemoMode } from '@/lib/api'
import {
  createDeployNode,
  createDeployRoute,
  createDeployRun,
  createDeployRunStub,
  deleteDeployNode,
  deleteDeployRoute,
  generateDeployKey,
  listComposeFiles,
  listDeployKeys,
  listDeployNodes,
  listDeployRoutes,
  type ApiDeployNode,
  type ApiDeployRoute,
  type ApiDeploySshKey,
} from '@/lib/deployApi'
import { runDeploySimulation } from '@/lib/deploySimulation'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import { StatusLabel } from './statusLabel'
import type {
  DeployAction,
  DeployHost,
  DeployPipelineStage,
  DeployRun,
  DeployRunStatus,
} from '@/types/studio'

function uid(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function hostLabel(h: { user?: string; host: string; port?: number; ssh_user?: string }) {
  const user = h.user ?? h.ssh_user ?? 'everflow'
  const port = h.port ?? 22
  return `${user}@${h.host}${port !== 22 ? `:${port}` : ''}`
}

function apiNodeToHost(n: ApiDeployNode): DeployHost {
  const status =
    n.status === 'online' || n.status === 'offline' ? n.status : ('unknown' as const)
  return {
    id: n.id,
    name: n.name,
    host: n.host,
    status,
    user: n.ssh_user,
    port: n.port,
    tags: n.tags ?? [],
    orchestrator: 'podman-compose',
  }
}

export function DeployPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const useApi = Boolean(project?.fromApi) && !isDemoMode()
  const sandboxRunning = project?.sandboxStatus === 'running'

  const state = useProjectStudio(projectId)
  const addHost = useStudioDemoStore((s) => s.addHost)
  const removeHost = useStudioDemoStore((s) => s.removeHost)
  const saveDeployRun = useStudioDemoStore((s) => s.saveDeployRun)
  const finalizeDeployRun = useStudioDemoStore((s) => s.finalizeDeployRun)

  const demoHosts = state.deployHosts
  const demoComposeFiles = state.composeFiles
  const envEntries = state.envEntries
  const deployRuns = state.deployRuns ?? []
  const deployServices = state.deployServices ?? []
  const deploys = state.deploys

  const [apiNodes, setApiNodes] = useState<ApiDeployNode[]>([])
  const [apiKeys, setApiKeys] = useState<ApiDeploySshKey[]>([])
  const [apiCompose, setApiCompose] = useState<string[]>([])
  const [apiRoutes, setApiRoutes] = useState<ApiDeployRoute[]>([])
  const [apiLoading, setApiLoading] = useState(false)
  const [keyBusy, setKeyBusy] = useState(false)

  const hosts = useApi ? apiNodes.map(apiNodeToHost) : demoHosts
  const composeFiles = useApi
    ? apiCompose.length
      ? apiCompose
      : ['docker-compose.yml']
    : demoComposeFiles

  const [hostId, setHostId] = useState(hosts[0]?.id ?? '')
  const [env, setEnv] = useState<string>('Preview')
  const [composeFile, setComposeFile] = useState(
    defaultComposeForEnv('Preview', composeFiles),
  )
  const [attachedIds, setAttachedIds] = useState<string[]>(() =>
    envEntries.filter((e) => e.kind === 'secret' || e.key.includes('API')).map((e) => e.id).slice(0, 2),
  )
  const [ctxTab, setCtxTab] = useState<'services' | 'env' | 'history' | 'compose' | 'routes'>(
    useApi ? 'routes' : 'services',
  )

  const [stages, setStages] = useState<DeployPipelineStage[]>([])
  const [logLines, setLogLines] = useState<string[]>([
    useApi
      ? 'Ready. Generate an SSH key, add a node, map domains, then Deploy over SSH.'
      : 'Ready. Select a host and run Deploy, Validate, Redeploy, or Stop.',
    useApi
      ? 'API mode: keys/nodes/routes persist; Deploy runs docker compose via SSH + Traefik routes.'
      : 'Pipeline runs are simulated until a remote host is connected.',
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

  const [routeHost, setRouteHost] = useState('')
  const [routeService, setRouteService] = useState('')
  const [routePort, setRoutePort] = useState('80')
  const [routePrefix, setRoutePrefix] = useState('/')

  const selectedHost = hosts.find((h) => h.id === hostId) ?? hosts[0]
  const latestKey = apiKeys[0] ?? null

  const refreshApi = useCallback(async () => {
    if (!useApi || !projectId) return
    const [keys, nodes, composeRes] = await Promise.all([
      listDeployKeys(projectId).catch(() => [] as ApiDeploySshKey[]),
      listDeployNodes(projectId).catch(() => [] as ApiDeployNode[]),
      listComposeFiles(projectId).catch(() => ({ files: [] as string[] })),
    ])
    setApiKeys(keys)
    setApiNodes(nodes)
    setApiCompose(composeRes.files ?? [])
    setHostId((prev) => {
      if (prev && nodes.some((n) => n.id === prev)) return prev
      return nodes[0]?.id ?? ''
    })
  }, [useApi, projectId])

  const refreshRoutes = useCallback(async () => {
    if (!useApi || !projectId || !selectedHost?.id) {
      setApiRoutes([])
      return
    }
    try {
      const routes = await listDeployRoutes(projectId, selectedHost.id)
      setApiRoutes(routes)
    } catch {
      setApiRoutes([])
    }
  }, [useApi, projectId, selectedHost?.id])

  useEffect(() => {
    if (!useApi) return
    setApiLoading(true)
    void refreshApi().finally(() => setApiLoading(false))
  }, [useApi, refreshApi])

  useEffect(() => {
    if (!useApi) return
    void refreshRoutes()
  }, [useApi, refreshRoutes])

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

  const onGenerateKey = async () => {
    if (!useApi || !projectId) return
    if (!sandboxRunning) {
      pushToast('Start the sandbox first', {
        description: 'SSH keys are generated inside the project sandbox.',
        kind: 'warning',
      })
      return
    }
    setKeyBusy(true)
    try {
      const key = await generateDeployKey(projectId)
      setApiKeys((prev) => [key, ...prev.filter((k) => k.id !== key.id)])
      setLogLines((prev) => [
        ...prev,
        `Generated deploy key ${key.fingerprint}`,
        'Install the public key on each host (~/.ssh/authorized_keys).',
      ])
      pushToast('Deploy key generated', {
        description: key.fingerprint,
        kind: 'success',
      })
    } catch (e) {
      pushToast('Key generation failed', {
        description: e instanceof Error ? e.message : 'Unknown error',
        kind: 'danger',
      })
    } finally {
      setKeyBusy(false)
    }
  }

  const startApiDeploy = async (action: DeployAction) => {
    if (!selectedHost) {
      pushToast('Select a remote node', { kind: 'warning' })
      return
    }
    if (!composeFile) {
      pushToast('Select a compose file', { kind: 'warning' })
      return
    }
    if (apiRoutes.length === 0) {
      pushToast('Add at least one domain→service route', { kind: 'warning' })
      setCtxTab('routes')
      return
    }
    setRunning(true)
    setRunStatus('running')
    setStages([
      { id: 'validate', name: 'Validate', status: 'running' },
      { id: 'ssh', name: 'SSH deploy', status: 'pending' },
    ])
    setLogLines([
      `Deploying to ${selectedHost.name} (${action})…`,
      `compose=${composeFile}`,
      `routes=${apiRoutes.length}`,
    ])
    try {
      // Validate first via stub record, then execute SSH compose-up.
      await createDeployRunStub(projectId, {
        node_id: selectedHost.id,
        compose_file: composeFile,
        action,
      })
      setStages([
        { id: 'validate', name: 'Validate', status: 'ok' },
        { id: 'ssh', name: 'SSH deploy', status: 'running' },
      ])
      const result = await createDeployRun(projectId, {
        node_id: selectedHost.id,
        compose_file: composeFile,
        dry_run: action === 'validate',
      })
      setLogLines((prev) => [...prev, ...(result.log_lines || [])])
      if (result.ok) {
        setStages([
          { id: 'validate', name: 'Validate', status: 'ok' },
          { id: 'ssh', name: 'SSH deploy', status: 'ok' },
        ])
        setRunStatus('ok')
        pushToast(action === 'validate' ? 'Validate completed' : 'Deploy completed', {
          description: result.remote_dir,
          kind: 'success',
        })
      } else {
        setStages([
          { id: 'validate', name: 'Validate', status: 'ok' },
          { id: 'ssh', name: 'SSH deploy', status: 'err' },
        ])
        setRunStatus('err')
        pushToast('Deploy failed', {
          description: result.error || 'Remote compose failed',
          kind: 'danger',
        })
      }
    } catch (e) {
      setStages([
        { id: 'validate', name: 'Validate', status: 'err' },
        { id: 'ssh', name: 'SSH deploy', status: 'err' },
      ])
      setLogLines((prev) => [
        ...prev,
        `ERROR: ${e instanceof Error ? e.message : 'deploy failed'}`,
      ])
      setRunStatus('err')
      pushToast('Deploy failed', {
        description: e instanceof Error ? e.message : 'Unknown error',
        kind: 'danger',
      })
    } finally {
      setRunning(false)
    }
  }

  const startRun = async (action: DeployAction) => {
    if (useApi) {
      await startApiDeploy(action)
      return
    }
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
            description: result.url ?? `${action} on ${selectedHost.name}`,
            kind: 'success',
          },
        )
        if (result.services.length) setCtxTab('services')
      } else if (result.status === 'err') {
        pushToast('Pipeline failed', { description: 'See log for details.', kind: 'danger' })
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

  const submitHost = async () => {
    if (!hostName.trim() || !hostAddr.trim()) return
    const tags = hostTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    if (useApi) {
      try {
        const node = await createDeployNode(projectId, {
          name: hostName.trim(),
          host: hostAddr.trim(),
          ssh_user: hostUser.trim() || 'everflow',
          port: Number(hostPort) || 22,
          tags,
        })
        setApiNodes((prev) => [node, ...prev])
        setHostId(node.id)
        pushToast('Node added', { kind: 'success' })
      } catch (e) {
        pushToast('Failed to add node', {
          description: e instanceof Error ? e.message : 'Unknown error',
          kind: 'danger',
        })
        return
      }
    } else {
      addHost(projectId, {
        name: hostName.trim(),
        host: hostAddr.trim(),
        user: hostUser.trim() || 'everflow',
        port: Number(hostPort) || 22,
        tags,
        orchestrator: 'podman-compose',
      })
      pushToast('Host added', { kind: 'success' })
    }
    setHostName('')
    setHostAddr('')
    setHostUser('everflow')
    setHostPort('22')
    setHostTags('')
    setHostOpen(false)
  }

  const onRemoveHost = async (id: string) => {
    if (useApi) {
      try {
        await deleteDeployNode(projectId, id)
        setApiNodes((prev) => prev.filter((n) => n.id !== id))
        if (hostId === id) setHostId('')
        pushToast('Node removed', { kind: 'warning' })
      } catch (e) {
        pushToast('Failed to remove node', {
          description: e instanceof Error ? e.message : 'Unknown error',
          kind: 'danger',
        })
      }
      return
    }
    removeHost(projectId, id)
    if (hostId === id) setHostId('')
    pushToast('Host removed', { kind: 'warning' })
  }

  const submitRoute = async () => {
    if (!useApi || !selectedHost || !routeHost.trim() || !routeService.trim()) return
    try {
      const route = await createDeployRoute(projectId, selectedHost.id, {
        host_header: routeHost.trim(),
        service_name: routeService.trim(),
        service_port: Number(routePort) || 80,
        path_prefix: routePrefix.trim() || '/',
      })
      setApiRoutes((prev) => [...prev, route])
      setRouteHost('')
      setRouteService('')
      setRoutePort('80')
      setRoutePrefix('/')
      pushToast('Route saved', { kind: 'success' })
    } catch (e) {
      pushToast('Failed to save route', {
        description: e instanceof Error ? e.message : 'Unknown error',
        kind: 'danger',
      })
    }
  }

  const showEmpty = hosts.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <div>
          <span className="section-label" style={{ margin: 0 }}>
            Remote deploy
          </span>
          <div className="lc-meta" style={{ marginTop: 2 }}>
            {useApi
              ? apiLoading
                ? 'Loading deploy config…'
                : hosts.length === 0
                  ? 'Generate an SSH key and add a remote node'
                  : 'Keys & nodes from API · Deploy runs SSH compose + Traefik routes'
              : hosts.length === 0
                ? 'Connect a remote host to deploy'
                : 'podman-compose on another host · simulated pipeline (no live SSH yet)'}
          </div>
        </div>
        <div className="deploy-actions">
          {useApi && (
            <Button
              variant="secondary"
              size="sm"
              isLoading={keyBusy}
              isDisabled={keyBusy || !sandboxRunning}
              onClick={() => void onGenerateKey()}
            >
              Generate key
            </Button>
          )}
          {running && !useApi && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => abortRef.current?.abort()}
            >
              Cancel
            </Button>
          )}
          {!useApi && (
            <>
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
            </>
          )}
          <Button
            variant="primary"
            size="sm"
            isLoading={running}
            isDisabled={running || !selectedHost}
            onClick={() => void startRun('up')}
          >
            Deploy
          </Button>
        </div>
      </div>

      {showEmpty ? (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <EmptySplash
            title={useApi ? 'No deploy nodes' : 'No remote hosts'}
            body={
              useApi
                ? latestKey
                  ? `Key ready (${latestKey.fingerprint}). Install the public key on the host, then add a node.`
                  : 'Generate an SSH deploy key in the sandbox, then add a remote node. Install the public key on the host before deploying.'
                : 'Add a remote host where Everflow can run podman-compose stacks.'
            }
            primaryLabel={useApi ? (latestKey ? 'Add node' : 'Generate key') : 'Add host'}
            onPrimary={() => {
              if (useApi) {
                if (latestKey) setHostOpen(true)
                else void onGenerateKey()
              } else setHostOpen(true)
            }}
            secondaryLabel={
              useApi ? (latestKey ? 'Generate new key' : 'Add node') : undefined
            }
            onSecondary={
              useApi
                ? () => {
                    if (latestKey) void onGenerateKey()
                    else setHostOpen(true)
                  }
                : undefined
            }
          />
          {useApi && latestKey && (
            <div style={{ padding: '0 24px 24px', maxWidth: 720, margin: '0 auto' }}>
              <div className="section-label">Install this public key</div>
              <TextArea
                aria-label="Deploy public key"
                value={latestKey.public_key}
                readOnly
                resizeOrientation="vertical"
                rows={3}
                style={{ fontFamily: 'var(--mono)', fontSize: 11 }}
              />
              <Button
                variant="link"
                size="sm"
                style={{ paddingInline: 0 }}
                onClick={() => {
                  void navigator.clipboard?.writeText(latestKey.public_key)
                  pushToast('Public key copied', { kind: 'info' })
                }}
              >
                Copy for ~/.ssh/authorized_keys
              </Button>
            </div>
          )}
        </div>
      ) : (
        <div className="deploy-workbench">
          <aside className="deploy-sidebar">
            <div className="deploy-sidebar-scroll">
              {!useApi && (
                <>
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
                </>
              )}

              {useApi && latestKey && (
                <>
                  <div className="section-label" style={{ marginTop: 0 }}>
                    Deploy public key
                  </div>
                  <p className="lc-meta" style={{ marginTop: 0 }}>
                    Fingerprint: {latestKey.fingerprint}
                  </p>
                  <TextArea
                    aria-label="Deploy public key"
                    value={latestKey.public_key}
                    readOnly
                    resizeOrientation="vertical"
                    rows={4}
                    style={{ fontFamily: 'var(--mono)', fontSize: 11 }}
                  />
                  <Button
                    variant="link"
                    size="sm"
                    style={{ paddingInline: 0 }}
                    onClick={() => {
                      void navigator.clipboard?.writeText(latestKey.public_key)
                      pushToast('Public key copied', { kind: 'info' })
                    }}
                  >
                    Copy for authorized_keys
                  </Button>
                </>
              )}

              <div className="section-label">
                {useApi ? 'Nodes' : 'Hosts'}
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
                  {!useApi && h.status === 'online' && (
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
                  {!useApi && (
                    <div className="lc-meta" style={{ marginTop: 4 }}>
                      last seen {h.lastSeen ?? '—'}
                    </div>
                  )}
                  <Button
                    variant="link"
                    isDanger
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      void onRemoveHost(h.id)
                    }}
                  >
                    Remove
                  </Button>
                </div>
              ))}

              {!useApi && (
                <>
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
                </>
              )}
            </div>
          </aside>

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
                    ? useApi
                      ? `${selectedHost.name} · ${apiRoutes.length} routes`
                      : `${selectedHost.name} · ${env} · ${attachedIds.length} env attach`
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

          <aside className="deploy-inspector">
            <Tabs
              activeKey={ctxTab}
              onSelect={(_e, k) => setCtxTab(k as typeof ctxTab)}
              variant="secondary"
              className="panel-pf-tabs"
            >
              {useApi ? (
                <Tab eventKey="routes" title={<TabTitleText>Routes</TabTitleText>} />
              ) : (
                <Tab eventKey="services" title={<TabTitleText>Services</TabTitleText>} />
              )}
              {!useApi && <Tab eventKey="env" title={<TabTitleText>Env</TabTitleText>} />}
              {!useApi && <Tab eventKey="history" title={<TabTitleText>History</TabTitleText>} />}
              <Tab eventKey="compose" title={<TabTitleText>Compose</TabTitleText>} />
            </Tabs>
            <div className="deploy-inspector-body">
              {ctxTab === 'routes' && useApi && (
                <>
                  <p className="lc-meta" style={{ marginTop: 0 }}>
                    Map a domain (Host header) to a compose service on this node.
                  </p>
                  <FormGroup label="Domain / host header" fieldId="dr-host">
                    <TextInput
                      id="dr-host"
                      value={routeHost}
                      onChange={(_e, v) => setRouteHost(v)}
                      placeholder="app.example.com"
                    />
                  </FormGroup>
                  <FormGroup label="Service name" fieldId="dr-svc" style={{ marginTop: 8 }}>
                    <TextInput
                      id="dr-svc"
                      value={routeService}
                      onChange={(_e, v) => setRouteService(v)}
                      placeholder="web"
                    />
                  </FormGroup>
                  <FormGroup label="Service port" fieldId="dr-port" style={{ marginTop: 8 }}>
                    <TextInput
                      id="dr-port"
                      value={routePort}
                      onChange={(_e, v) => setRoutePort(v)}
                    />
                  </FormGroup>
                  <FormGroup label="Path prefix" fieldId="dr-path" style={{ marginTop: 8 }}>
                    <TextInput
                      id="dr-path"
                      value={routePrefix}
                      onChange={(_e, v) => setRoutePrefix(v)}
                    />
                  </FormGroup>
                  <Button
                    variant="secondary"
                    size="sm"
                    style={{ marginTop: 10 }}
                    isDisabled={!routeHost.trim() || !routeService.trim() || !selectedHost}
                    onClick={() => void submitRoute()}
                  >
                    Add route
                  </Button>
                  <div style={{ marginTop: 12 }}>
                    {apiRoutes.length === 0 ? (
                      <p className="lc-meta">No routes yet.</p>
                    ) : (
                      apiRoutes.map((r) => (
                        <div className="deploy-svc-row" key={r.id}>
                          <div className="lc-row">
                            <strong style={{ fontFamily: 'var(--mono)' }}>{r.host_header}</strong>
                            <Button
                              variant="link"
                              isDanger
                              size="sm"
                              onClick={() => {
                                if (!selectedHost) return
                                void deleteDeployRoute(projectId, selectedHost.id, r.id)
                                  .then(() =>
                                    setApiRoutes((prev) => prev.filter((x) => x.id !== r.id)),
                                  )
                                  .catch((e) =>
                                    pushToast('Failed to delete route', {
                                      description:
                                        e instanceof Error ? e.message : 'Unknown error',
                                      kind: 'danger',
                                    }),
                                  )
                              }}
                            >
                              Remove
                            </Button>
                          </div>
                          <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                            → {r.service_name}:{r.service_port}
                            {r.path_prefix !== '/' ? ` ${r.path_prefix}` : ''}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}

              {ctxTab === 'services' && !useApi && (
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

              {ctxTab === 'env' && !useApi && (
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

              {ctxTab === 'history' && !useApi && (
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
                <pre className="deploy-compose-pre">
                  {useApi
                    ? composeFile
                      ? `# discovered\n${composeFile}\n`
                      : 'No compose files discovered under /workspace.'
                    : composeSnippet(composeFile)}
                </pre>
              )}
            </div>
          </aside>
        </div>
      )}

      <CreateResourceModal
        isOpen={hostOpen}
        title={useApi ? 'Add deploy node' : 'Add remote host'}
        onClose={() => setHostOpen(false)}
        onSubmit={() => void submitHost()}
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
