import type {
  DeployAction,
  DeployHost,
  DeployPipelineStage,
  DeployService,
  EnvEntry,
} from '@/types/studio'

export type SimUpdate = {
  stages: DeployPipelineStage[]
  logLines: string[]
  status: 'running' | 'ok' | 'err' | 'cancelled'
}

export type SimResult = SimUpdate & {
  services: DeployService[]
  url?: string
}

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const t = window.setTimeout(() => resolve(), ms)
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(t)
        reject(new DOMException('Aborted', 'AbortError'))
      },
      { once: true },
    )
  })
}

function ts() {
  return new Date().toLocaleTimeString()
}

function stageNames(action: DeployAction): string[] {
  if (action === 'validate') {
    return ['Connect', 'Validate compose']
  }
  if (action === 'down') {
    return ['Connect', 'Graceful stop', 'podman-compose down', 'Cleanup networks']
  }
  // up + redeploy
  return [
    'Connect',
    'Validate compose',
    'Sync files',
    'podman-compose pull',
    action === 'redeploy' ? 'Recreate stack' : 'podman-compose up -d',
    'Health checks',
    'Publish URL',
  ]
}

function servicesFor(
  composeFile: string,
  env: string,
  hostId: string,
  running: boolean,
): DeployService[] {
  const status = running ? 'running' : 'stopped'
  const base: Omit<DeployService, 'id'>[] = composeFile.includes('preview')
    ? [
        { name: 'web', image: 'everflow/web:preview', ports: '5173:5173', status, stack: composeFile, env, hostId },
        { name: 'api', image: 'everflow/api:preview', ports: '8000:8000', status, stack: composeFile, env, hostId },
      ]
    : composeFile.includes('staging')
      ? [
          { name: 'web', image: 'everflow/web:staging', ports: '80:8080', status, stack: composeFile, env, hostId },
          { name: 'api', image: 'everflow/api:staging', ports: '80:8000', status, stack: composeFile, env, hostId },
          { name: 'worker', image: 'everflow/worker:staging', ports: '—', status, stack: composeFile, env, hostId },
          { name: 'redis', image: 'redis:7-alpine', ports: '6379:6379', status, stack: composeFile, env, hostId },
        ]
      : [
          { name: 'nginx-proxy', image: 'nginx:alpine', ports: '80:80', status, stack: composeFile, env, hostId },
          { name: 'node-api', image: 'everflow/api:latest', ports: '8000:8000', status, stack: composeFile, env, hostId },
          { name: 'postgres-db', image: 'postgres:16', ports: '5432:5432', status, stack: composeFile, env, hostId },
          { name: 'redis-cache', image: 'redis:7-alpine', ports: '6379:6379', status, stack: composeFile, env, hostId },
        ]
  return base.map((s, i) => ({ ...s, id: `svc-${hostId}-${env}-${i}` }))
}

function logsForStage(
  stage: string,
  opts: {
    host: DeployHost
    composeFile: string
    env: string
    action: DeployAction
    attached: EnvEntry[]
  },
): string[] {
  const { host, composeFile, env, attached } = opts
  const addr = `${host.user ?? 'everflow'}@${host.host}`
  switch (stage) {
    case 'Connect':
      return [
        `[${ts()}] ssh ${addr} — opening session (demo)`,
        `[${ts()}] host fingerprint ok · orchestrator=${host.orchestrator ?? 'podman-compose'}`,
      ]
    case 'Validate compose':
      return [
        `[${ts()}] reading ${composeFile}`,
        `[${ts()}] schema ok ·  services declared · env=${env}`,
      ]
    case 'Sync files':
      return [
        `[${ts()}] rsync project → ${addr}:/opt/everflow/stacks/${env.toLowerCase()}`,
        `[${ts()}] transferred compose + assets (demo)`,
      ]
    case 'podman-compose pull':
      return [
        `[${ts()}] podman-compose -f ${composeFile} pull`,
        `[${ts()}] images up to date`,
      ]
    case 'podman-compose up -d':
    case 'Recreate stack':
      return [
        ...attached.map(
          (e) =>
            `[${ts()}] [env] injecting ${e.key}${e.kind === 'secret' ? ' (masked)' : `=${e.value}`}`,
        ),
        `[${ts()}] podman-compose -f ${composeFile} ${stage.includes('Recreate') ? 'up -d --force-recreate' : 'up -d'}`,
        `[${ts()}] Creating network… Starting containers…`,
      ]
    case 'Health checks':
      return [
        `[${ts()}] probing /healthz on published ports`,
        `[${ts()}] all checks passed`,
      ]
    case 'Publish URL':
      return [
        `[${ts()}] publishing https://${env.toLowerCase()}.${host.name}.local`,
        `[${ts()}] route registered (demo)`,
      ]
    case 'Graceful stop':
      return [`[${ts()}] signaling containers for ${env}…`]
    case 'podman-compose down':
      return [`[${ts()}] podman-compose -f ${composeFile} down`, `[${ts()}] containers removed`]
    case 'Cleanup networks':
      return [`[${ts()}] pruned unused networks for stack`]
    default:
      return [`[${ts()}] ${stage}`]
  }
}

export async function runDeploySimulation(
  opts: {
    host: DeployHost
    composeFile: string
    env: string
    action: DeployAction
    attached: EnvEntry[]
    /** Force failure after this stage index (0-based). Offline host fails at connect. */
    forceFailAt?: number
  },
  onUpdate: (u: SimUpdate) => void,
  signal?: AbortSignal,
): Promise<SimResult> {
  const names = stageNames(opts.action)
  let stages: DeployPipelineStage[] = names.map((name, i) => ({
    id: `s${i + 1}`,
    name,
    status: 'pending' as const,
  }))
  let logLines: string[] = [
    `[${ts()}] pipeline start · action=${opts.action} · host=${opts.host.name} · ${opts.composeFile}`,
  ]
  onUpdate({ stages, logLines, status: 'running' })

  const failAt =
    opts.host.status === 'offline'
      ? 0
      : opts.forceFailAt ?? (opts.action === 'up' && Math.random() < 0.12 ? 3 : -1)

  for (let i = 0; i < names.length; i++) {
    if (signal?.aborted) {
      stages = stages.map((s, idx) =>
        idx < i ? s : idx === i ? { ...s, status: 'skipped' } : { ...s, status: 'skipped' },
      )
      logLines = [...logLines, `[${ts()}] cancelled by user`]
      onUpdate({ stages, logLines, status: 'cancelled' })
      return { stages, logLines, status: 'cancelled', services: [] }
    }

    stages = stages.map((s, idx) =>
      idx === i ? { ...s, status: 'running' } : s,
    )
    onUpdate({ stages, logLines, status: 'running' })

    const chunk = logsForStage(names[i], opts)
    for (const line of chunk) {
      await sleep(120 + Math.random() * 80, signal)
      logLines = [...logLines, line]
      onUpdate({ stages, logLines, status: 'running' })
    }

    if (i === failAt) {
      const errMsg =
        opts.host.status === 'offline'
          ? `[${ts()}] ERROR: host ${opts.host.name} is offline — cannot open SSH session`
          : `[${ts()}] ERROR: stage "${names[i]}" failed (demo simulated fault)`
      logLines = [...logLines, errMsg]
      stages = stages.map((s, idx) =>
        idx === i
          ? { ...s, status: 'err', log: errMsg }
          : idx > i
            ? { ...s, status: 'skipped' }
            : s,
      )
      onUpdate({ stages, logLines, status: 'err' })
      return { stages, logLines, status: 'err', services: [] }
    }

    stages = stages.map((s, idx) =>
      idx === i ? { ...s, status: 'ok', log: chunk[chunk.length - 1] } : s,
    )
    onUpdate({ stages, logLines, status: 'running' })
    await sleep(200, signal)
  }

  logLines = [...logLines, `[${ts()}] pipeline complete`]
  const running = opts.action !== 'down' && opts.action !== 'validate'
  const services =
    opts.action === 'validate'
      ? []
      : servicesFor(opts.composeFile, opts.env, opts.host.id, running)
  const url =
    running
      ? `https://${opts.env.toLowerCase()}.${opts.host.name}.local`
      : undefined
  onUpdate({ stages, logLines, status: 'ok' })
  return { stages, logLines, status: 'ok', services, url }
}
