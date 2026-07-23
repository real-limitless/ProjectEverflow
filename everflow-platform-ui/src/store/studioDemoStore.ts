import { useEffect } from 'react'
import { create } from 'zustand'
import { getStudioExtras } from '@/data/studioExtras'
import { getProject } from '@/data/projects'
import { categoryToLegacyKind, deriveN8nGraph } from '@/lib/n8nImport'
import type {
  AgentDefinition,
  BackgroundJob,
  DeployHost,
  DeployRecord,
  DeployRun,
  DeployService,
  EnvEntry,
  HttpToolDef,
  EmbedStatus,
  KnowledgeCanvas,
  KnowledgeDoc,
  KnowledgeOrigin,
  McpServerDef,
  MindMap,
  ProjectStudioState,
  PullRequest,
  RepoIssue,
  SqlResult,
  TestCase,
  TestSuite,
  WorkflowDef,
  WorkflowRun,
  WfNodeKind,
} from '@/types/studio'

function uid(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** Stable fallback seeds so Zustand getSnapshot never allocates a new object each call. */
const seedCache = new Map<string, ProjectStudioState>()

function getStableSeed(projectId: string): ProjectStudioState {
  let seeded = seedCache.get(projectId)
  if (!seeded) {
    seeded = seedProject(projectId)
    seedCache.set(projectId, seeded)
  }
  return seeded
}

function resolveProjectId(projectId: string | null | undefined): string {
  return projectId || 'default'
}

/** Demo seed ids: iss-42 / pr-12 / *-sec-*; user-created ids use uid() → prefix-ts-rand. */
function isDemoCatalogIssueId(id: string): boolean {
  return /^iss-\d+$/.test(id) || id.startsWith('iss-sec-')
}

function isDemoCatalogPrId(id: string): boolean {
  return /^pr-\d+$/.test(id) || id.startsWith('pr-sec-')
}

const DEMO_COMPOSE_FILES = [
  'podman-compose.yml',
  'podman-compose.staging.yml',
  'compose.preview.yml',
] as const

function isDemoCatalogEnvId(id: string): boolean {
  return /^env-\d+$/.test(id) || /^sec-\d+$/.test(id)
}

function isDemoCatalogTestSuiteId(id: string): boolean {
  return /^suite-\d+$/.test(id)
}

function isDemoCatalogTestCaseId(id: string): boolean {
  return /^tc-\d+$/.test(id)
}

function isDemoCatalogJobId(id: string): boolean {
  return /^job-\d+/.test(id)
}

function isDemoCatalogDeployHostId(id: string): boolean {
  return /^host-\d+$/.test(id)
}

function isDemoCatalogDeployRunId(id: string): boolean {
  return id.startsWith('run-seed-')
}

function isDemoCatalogDeployId(id: string): boolean {
  return /^dep-\d+$/.test(id)
}

function isDemoCatalogDeployServiceId(id: string): boolean {
  return /^svc-p-\d+$/.test(id)
}

function isDemoComposeFiles(files: string[]): boolean {
  if (files.length !== DEMO_COMPOSE_FILES.length) return false
  const sorted = [...files].sort()
  const demo = [...DEMO_COMPOSE_FILES].sort()
  return sorted.every((f, i) => f === demo[i])
}

function stripDemoCatalog(state: ProjectStudioState): ProjectStudioState {
  const hadDemoCatalog =
    state.issues.some((i) => isDemoCatalogIssueId(i.id)) ||
    state.pullRequests.some((pr) => isDemoCatalogPrId(pr.id)) ||
    state.agents.some((a) => a.source === 'demo' || /^a\d+$/.test(a.id)) ||
    state.mcps.some((m) => /^mcp-\d+$/.test(m.id)) ||
    state.envEntries.some((e) => isDemoCatalogEnvId(e.id)) ||
    state.testSuites.some(
      (s) =>
        isDemoCatalogTestSuiteId(s.id) ||
        s.cases.some((c) => isDemoCatalogTestCaseId(c.id)),
    ) ||
    (state.lastTestRun != null &&
      isDemoCatalogTestSuiteId(state.lastTestRun.suiteId)) ||
    state.jobs.some((j) => isDemoCatalogJobId(j.id)) ||
    state.deployHosts.some((h) => isDemoCatalogDeployHostId(h.id)) ||
    state.deployRuns.some((r) => isDemoCatalogDeployRunId(r.id)) ||
    state.deployServices.some((s) => isDemoCatalogDeployServiceId(s.id)) ||
    state.deploys.some((d) => isDemoCatalogDeployId(d.id)) ||
    isDemoComposeFiles(state.composeFiles) ||
    (state.deployTimeline.length > 0 &&
      (state.deployHosts.some((h) => isDemoCatalogDeployHostId(h.id)) ||
        state.deployRuns.some((r) => isDemoCatalogDeployRunId(r.id)) ||
        state.deploys.some((d) => isDemoCatalogDeployId(d.id)) ||
        state.deployServices.some((s) => isDemoCatalogDeployServiceId(s.id))))

  if (!hadDemoCatalog) return state

  const issues = state.issues.filter((i) => !isDemoCatalogIssueId(i.id))
  const pullRequests = state.pullRequests.filter((pr) => !isDemoCatalogPrId(pr.id))
  const agents = state.agents.filter((a) => a.source !== 'demo' && !/^a\d+$/.test(a.id))
  const mcps = state.mcps.filter((m) => !/^mcp-\d+$/.test(m.id))
  const envEntries = state.envEntries.filter((e) => !isDemoCatalogEnvId(e.id))
  const testSuites = state.testSuites
    .filter((s) => !isDemoCatalogTestSuiteId(s.id))
    .map((s) => ({
      ...s,
      cases: s.cases.filter((c) => !isDemoCatalogTestCaseId(c.id)),
    }))
  const lastTestRun =
    state.lastTestRun && isDemoCatalogTestSuiteId(state.lastTestRun.suiteId)
      ? null
      : state.lastTestRun
  const jobs = state.jobs.filter((j) => !isDemoCatalogJobId(j.id))
  const deployHosts = state.deployHosts.filter((h) => !isDemoCatalogDeployHostId(h.id))
  const deployRuns = state.deployRuns.filter((r) => !isDemoCatalogDeployRunId(r.id))
  const deployServices = state.deployServices.filter((s) => !isDemoCatalogDeployServiceId(s.id))
  const deploys = state.deploys.filter((d) => !isDemoCatalogDeployId(d.id))
  const composeFiles = isDemoComposeFiles(state.composeFiles) ? [] : state.composeFiles
  const deployTimeline =
    state.deployHosts.some((h) => isDemoCatalogDeployHostId(h.id)) ||
    state.deployRuns.some((r) => isDemoCatalogDeployRunId(r.id)) ||
    state.deploys.some((d) => isDemoCatalogDeployId(d.id)) ||
    state.deployServices.some((s) => isDemoCatalogDeployServiceId(s.id))
      ? []
      : state.deployTimeline

  return {
    ...state,
    issues,
    pullRequests,
    agents,
    mcps,
    envEntries,
    testSuites,
    lastTestRun,
    jobs,
    deployHosts,
    deployRuns,
    deployServices,
    deploys,
    composeFiles,
    deployTimeline,
  }
}

function seedProject(projectId: string): ProjectStudioState {
  const d = getStudioExtras(projectId)
  const p = getProject(projectId)
  const primaryRepoId =
    p?.repos.find((r) => r.active)?.id || p?.repos[0]?.id || 'main'
  const secondaryRepos = (p?.repos || []).filter((r) => r.id !== primaryRepoId)
  /** API-backed projects must not get showcase issue/PR catalog noise. */
  const useDemoCatalog = !p?.fromApi

  const issues: RepoIssue[] = useDemoCatalog
    ? [
    {
      id: 'iss-42',
      number: 42,
      title: 'MetricCard warning at 67%',
      body: 'Thresholds fire too early on staging metrics. Repro: load dashboard with sample scrape.',
      status: 'open',
      labels: ['bug', 'frontend'],
      author: 'you',
      updatedAt: '2m ago',
      comments: [
        { id: 'c1', author: 'agent', body: 'Thresholds updated in PR draft — see Changes.', createdAt: '2m ago' },
      ],
      repoId: primaryRepoId,
    },
    {
      id: 'iss-41',
      number: 41,
      title: 'Document sandbox attach flow',
      body: 'Add runbook for first-time node attach.',
      status: 'open',
      labels: ['docs'],
      author: 'rafi',
      updatedAt: '1d ago',
      comments: [],
      repoId: primaryRepoId,
    },
    {
      id: 'iss-38',
      number: 38,
      title: 'Redis health flaky in CI',
      body: 'Ping timeout under load.',
      status: 'closed',
      labels: ['infra'],
      author: 'siti',
      updatedAt: '3d ago',
      comments: [],
      repoId: primaryRepoId,
    },
    // Light seeds so secondary repos are not empty when multi-repo
    ...secondaryRepos.slice(0, 2).map((r, i) => ({
      id: `iss-sec-${r.id}`,
      number: 20 + i,
      title: `[${r.label}] Follow up items`,
      body: `Demo issues for repository ${r.label}.`,
      status: 'open' as const,
      labels: ['triage'],
      author: 'you',
      updatedAt: '1d ago',
      comments: [] as RepoIssue['comments'],
      repoId: r.id,
    })),
  ]
    : []

  const pullRequests: PullRequest[] = useDemoCatalog
    ? [
    {
      id: 'pr-12',
      number: 12,
      title: 'Fix MetricCard warning threshold',
      body: 'Adjust band to 80% and add unit tests.',
      status: 'open',
      base: 'main',
      head: 'fix/metric-threshold',
      author: 'you',
      updatedAt: '2m ago',
      checks: [
        { name: 'lint', status: 'ok' },
        { name: 'unit', status: 'pending' },
        { name: 'preview', status: 'ok' },
      ],
      reviewStatus: 'pending',
      repoId: primaryRepoId,
    },
    {
      id: 'pr-11',
      number: 11,
      title: 'Wire nginx health checks',
      body: 'Probe /healthz on proxy.',
      status: 'merged',
      base: 'main',
      head: 'feat/nginx-health',
      author: 'you',
      updatedAt: 'yesterday',
      checks: [
        { name: 'lint', status: 'ok' },
        { name: 'unit', status: 'ok' },
      ],
      reviewStatus: 'approved',
      repoId: primaryRepoId,
    },
    {
      id: 'pr-10',
      number: 10,
      title: 'Draft: deploy pipeline UI',
      body: 'WIP remote compose stages.',
      status: 'draft',
      base: 'main',
      head: 'feat/deploy-pipeline',
      author: 'ayu',
      updatedAt: '2d ago',
      checks: [],
      reviewStatus: 'pending',
      repoId: primaryRepoId,
    },
    ...secondaryRepos.slice(0, 1).map((r) => ({
      id: `pr-sec-${r.id}`,
      number: 3,
      title: `[${r.label}] Align shared types`,
      body: `Demo PR scoped to ${r.label}.`,
      status: 'open' as const,
      base: 'main',
      head: 'chore/shared-types',
      author: 'you',
      updatedAt: '3d ago',
      checks: [{ name: 'lint', status: 'ok' as const }],
      reviewStatus: 'pending' as const,
      repoId: r.id,
    })),
  ]
    : []

  const commits = [
    {
      id: 'c-a91',
      hash: 'a91f3c2b8e4d',
      shortHash: 'a91f3c2',
      message: 'Fix MetricCard warning threshold',
      author: 'you',
      when: '2m ago',
      parents: ['c-b02'],
      branchLabels: ['fix/metric-threshold', 'HEAD'],
      files: ['src/MetricCard.tsx', 'src/MetricCard.test.tsx'],
      isHead: true,
      repoId: primaryRepoId,
    },
    {
      id: 'c-b02',
      hash: 'b02e881c1a90',
      shortHash: 'b02e881',
      message: 'Wire nginx health checks',
      author: 'you',
      when: 'yesterday',
      parents: ['c-c11'],
      branchLabels: ['main'],
      files: ['deploy/nginx.conf'],
      repoId: primaryRepoId,
    },
    {
      id: 'c-c11',
      hash: 'c11d404a77fe',
      shortHash: 'c11d404',
      message: 'Add metrics scrape workflow',
      author: 'rafi',
      when: '3d ago',
      parents: ['c-d20'],
      branchLabels: [],
      files: ['workflows/scrape.json'],
      repoId: primaryRepoId,
    },
    {
      id: 'c-d20',
      hash: 'd20f991e55aa',
      shortHash: 'd20f991',
      message: 'Initial studio layout',
      author: 'ayu',
      when: '1w ago',
      parents: [],
      branchLabels: [],
      files: ['src/App.tsx'],
      repoId: primaryRepoId,
    },
    {
      id: 'c-e33',
      hash: 'e33a102bb901',
      shortHash: 'e33a102',
      message: 'Experiment: dark chart tokens',
      author: 'you',
      when: '4d ago',
      parents: ['c-c11'],
      branchLabels: ['experiment/charts'],
      files: ['src/styles/charts.css'],
      repoId: primaryRepoId,
    },
    ...secondaryRepos.slice(0, 2).map((r, i) => ({
      id: `c-sec-${r.id}`,
      hash: `sec${i}0000000`,
      shortHash: `sec${i}000`,
      message: `Bootstrap ${r.label}`,
      author: 'you',
      when: `${i + 2}d ago`,
      parents: [] as string[],
      branchLabels: ['main', ...(i === 0 ? ['HEAD'] : [])],
      files: ['README.md'],
      isHead: i === 0,
      repoId: r.id,
    })),
  ]

  const workflows: WorkflowDef[] = d.workflows.map((w, i) => ({
    id: `wf-${i}`,
    name: w.name,
    status: w.status,
    trigger: w.trigger,
    runs: w.runs,
    nodes: d.wfNodes.map((n, j) => ({
      id: `n-${i}-${j}`,
      type: 'studio',
      position: { x: 80 + j * 180, y: 120 + (j % 2) * 40 },
      data: {
        label: n.label,
        kind: (n.cls === 'trigger'
          ? 'trigger'
          : n.cls === 'llm'
            ? 'llm'
            : n.cls === 'code'
              ? 'code'
              : n.cls === 'http'
                ? 'http'
                : 'unknown') as WfNodeKind,
        params: {},
      },
    })),
    edges: d.wfNodes.slice(0, -1).map((_, j) => ({
      id: `e-${i}-${j}`,
      source: `n-${i}-${j}`,
      target: `n-${i}-${j + 1}`,
    })),
  }))

  const workflowRuns: WorkflowRun[] = d.wfRuns.map((r) => ({
    ...r,
    workflowId: workflows[0]?.id ?? 'wf-0',
    log: [`started ${r.id}`, `status=${r.status}`, `duration=${r.dur}`],
  }))

  // API-backed projects start with no demo knowledge (real vault/RAG wiring).
  const useDemoKnowledge = !p?.fromApi

  const seedCanvases = useDemoKnowledge
    ? p?.canvases ?? [{ name: 'Architecture', desc: 'System sketch' }]
    : []
  const canvases: KnowledgeCanvas[] = seedCanvases.map((c, i) => ({
    id: `cv-${i}`,
    name: c.name,
    desc: c.desc,
    contentMd:
      i === 0
        ? `# ${c.name}\n\n${c.desc || 'Project knowledge document.'}\n\n## Overview\n\nUse this canvas as Markdown knowledge for the project chatbot. Edit in **Source** or review the rich **Preview**.\n\n## Notes\n\n- Chunk and embed when ready for retrieval\n- Upload PDFs for Unlimited OCR → Markdown conversion\n`
        : `# ${c.name}\n\n${c.desc || ''}\n`,
    origin: 'created' as KnowledgeOrigin,
    // First seed note is in chatbot knowledge; others are notes-only until indexed
    status: (i === 0 ? 'indexed' : 'ready') as EmbedStatus,
    chunks: i === 0 ? 42 : undefined,
    updatedAt: 'just now',
  }))

  if (useDemoKnowledge) {
    // Seed OCR document as a full canvas (knowledge document) — demo projects only
    canvases.unshift({
      id: 'cv-runbook',
      name: 'runbook.pdf',
      desc: 'Converted via Unlimited OCR',
      contentMd: `# Operations Runbook\n\n> Extracted from **runbook.pdf** via Unlimited OCR (demo).\n\n## Deploy checklist\n\n1. Confirm host health\n2. Apply compose stack\n3. Smoke-test preview URL\n\n## Rollback\n\n- Keep previous image tag\n- Restore env snapshot if needed\n\n## Contacts\n\n- On-call: platform team\n`,
      origin: 'ocr',
      status: 'indexed',
      chunks: 128,
      mime: 'application/pdf',
      sizeLabel: '2.4 MB',
      updatedAt: 'earlier',
    })
  }

  const docs: KnowledgeDoc[] = []

  const mindMaps: MindMap[] = useDemoKnowledge
    ? [
        {
          id: 'mm-1',
          name: 'Product map',
          mermaid: `mindmap
  root((${d.projectName || 'Project'}))
    Studio
      Agents
      Workflows
    Deploy
      Hosts
      Compose`,
          updatedAt: 'just now',
        },
        {
          id: 'mm-2',
          name: 'RAG pipeline',
          mermaid: `flowchart LR
  A[Upload / Canvas] --> B[OCR / Markdown]
  B --> C[Chunk]
  C --> D[Embed]
  D --> E[(Vector store)]
  E --> F[Chatbot retrieve]`,
          updatedAt: 'yesterday',
        },
      ]
    : []

  const tables = d.tables.map((t) => ({
    ...t,
    columns: t.name === 'users' ? ['id', 'email', 'role'] : ['name', 'status', 'cpu'],
  }))

  const jobs: BackgroundJob[] = useDemoCatalog
    ? d.jobs.map((j, i) => ({
        id: `job-${i}`,
        title: j.title,
        type: j.title.toLowerCase().includes('index') ? 'index' : 'custom',
        status: j.status as BackgroundJob['status'],
        progress: j.progress,
      }))
    : []

  // API projects use OpenCode live agents — never seed showcase "Coding Assistant" etc.
  const agents: AgentDefinition[] = useDemoCatalog
    ? d.agents.map((a) => ({
        id: a.id,
        name: a.name,
        role: a.name.includes('Deploy')
          ? 'reviewer'
          : a.name.includes('General')
            ? 'general'
            : 'coder',
        desc: a.desc,
        description: a.desc,
        systemPrompt: `You are ${a.name}. ${a.desc}. Be concise and safe.`,
        prompt: `You are ${a.name}. ${a.desc}. Be concise and safe.`,
        mode: 'all' as const,
        tools: ['file_read', 'git_status'],
        active: a.active,
        managed: false,
        source: 'demo' as const,
      }))
    : []

  const httpTools: HttpToolDef[] = useDemoCatalog
    ? d.httpTools.map((t, i) => ({
        id: `tool-${i}`,
        name: t.name,
        method: t.method,
        url: `https://api.example.com/${t.name}`,
        headers: '',
        on: t.on,
      }))
    : []

  const mcps: McpServerDef[] = useDemoCatalog
    ? d.mcps.map((m, i) => ({
        id: `mcp-${i}`,
        name: m.name,
        transport: m.transport,
        endpoint: m.transport.includes('stdio')
          ? 'npx -y @example/mcp'
          : 'https://mcp.example.com/sse',
        on: m.on,
      }))
    : []

  const envEntries: EnvEntry[] = useDemoCatalog
    ? [
        ...d.envVars.map((e, i) => ({
          id: `env-${i}`,
          key: e.key,
          value: e.value,
          kind: 'env' as const,
          attachedTo: [] as string[],
        })),
        ...d.secrets.map((e, i) => ({
          id: `sec-${i}`,
          key: e.key,
          value: e.value,
          kind: 'secret' as const,
          attachedTo: e.key.includes('DATABASE')
            ? ['postgres']
            : e.key.includes('STRIPE')
              ? ['billing']
              : ['llm'],
          revealed: false,
        })),
      ]
    : []

  const testSuites: TestSuite[] = useDemoCatalog
    ? [
    {
      id: 'suite-1',
      name: 'unit',
      cases: [
        {
          id: 'tc-1',
          name: 'MetricCard › warning threshold at 67%',
          type: 'unit',
          command: 'vitest run MetricCard',
          lastStatus: d.tests.failedN ? 'failed' : 'passed',
          error: d.tests.failedN ? 'expected 80, received 67' : undefined,
        },
        {
          id: 'tc-2',
          name: 'HealthCheck › redis ping timeout',
          type: 'unit',
          command: 'vitest run HealthCheck',
          lastStatus: d.tests.failed.includes('HealthCheck › redis ping timeout') ? 'failed' : 'passed',
          error: d.tests.failed.includes('HealthCheck › redis ping timeout') ? 'Timeout 2000ms' : undefined,
        },
        {
          id: 'tc-3',
          name: 'Auth › login happy path',
          type: 'unit',
          command: 'vitest run Auth',
          lastStatus: 'passed',
        },
      ],
    },
    {
      id: 'suite-2',
      name: 'e2e smoke',
      cases: [
        {
          id: 'tc-4',
          name: 'Playground loads dock',
          type: 'e2e',
          command: 'playwright test smoke',
          lastStatus: 'passed',
        },
      ],
    },
  ]
    : []

  const deployHosts: DeployHost[] = useDemoCatalog
    ? [
    {
      id: 'host-1',
      name: 'edge-01',
      host: 'edge-01.internal',
      status: 'online',
      user: 'everflow',
      port: 22,
      tags: ['edge', 'prod'],
      lastSeen: 'just now',
      orchestrator: 'podman-compose',
      cpuPct: 34,
      memPct: 52,
    },
    {
      id: 'host-2',
      name: 'gpu-lab',
      host: 'gpu-lab.lan',
      status: 'offline',
      user: 'lab',
      port: 22,
      tags: ['gpu'],
      lastSeen: '3h ago',
      orchestrator: 'podman-compose',
      cpuPct: 0,
      memPct: 12,
    },
    {
      id: 'host-3',
      name: 'staging-box',
      host: 'staging.internal',
      status: 'online',
      user: 'deploy',
      port: 22,
      tags: ['staging'],
      lastSeen: '1m ago',
      orchestrator: 'podman-compose',
      cpuPct: 18,
      memPct: 41,
    },
  ]
    : []

  const deploys: DeployRecord[] = useDemoCatalog
    ? d.deploys.map((dep, i) => ({
        id: `dep-${i}`,
        env: dep.env,
        url: dep.url,
        status: dep.status,
        when: dep.when,
        hostId: i === 0 ? 'host-1' : 'host-3',
        composeFile: i === 0 ? 'compose.preview.yml' : 'podman-compose.staging.yml',
        runId: `run-seed-${i}`,
      }))
    : []

  const deployRuns: DeployRun[] = useDemoCatalog
    ? [
    {
      id: 'run-seed-0',
      hostId: 'host-1',
      env: 'Preview',
      composeFile: 'compose.preview.yml',
      action: 'up',
      status: 'ok',
      startedAt: 'Just now',
      finishedAt: 'Just now',
      durationLabel: '12s',
      stages: [
        { id: 's1', name: 'Connect', status: 'ok' },
        { id: 's2', name: 'Validate compose', status: 'ok' },
        { id: 's3', name: 'podman-compose up -d', status: 'ok' },
        { id: 's4', name: 'Health checks', status: 'ok' },
      ],
      logLines: [
        '[seed] pipeline start · action=up · host=edge-01',
        '[seed] podman-compose -f compose.preview.yml up -d',
        '[seed] all checks passed',
        '[seed] pipeline complete',
      ],
      attachedEnvIds: envEntries.filter((e) => e.key === 'VITE_API_URL').map((e) => e.id),
    },
    {
      id: 'run-seed-1',
      hostId: 'host-3',
      env: 'Staging',
      composeFile: 'podman-compose.staging.yml',
      action: 'up',
      status: 'ok',
      startedAt: '3h ago',
      finishedAt: '3h ago',
      durationLabel: '28s',
      stages: [
        { id: 's1', name: 'Connect', status: 'ok' },
        { id: 's2', name: 'Validate compose', status: 'ok' },
        { id: 's3', name: 'podman-compose up -d', status: 'ok' },
      ],
      logLines: ['[seed] staging deploy completed'],
      attachedEnvIds: envEntries.filter((e) => e.kind === 'secret').slice(0, 1).map((e) => e.id),
    },
  ]
    : []

  const deployServices: DeployService[] = useDemoCatalog
    ? [
    {
      id: 'svc-p-0',
      name: 'web',
      image: 'everflow/web:preview',
      ports: '5173:5173',
      status: 'running',
      stack: 'compose.preview.yml',
      env: 'Preview',
      hostId: 'host-1',
    },
    {
      id: 'svc-p-1',
      name: 'api',
      image: 'everflow/api:preview',
      ports: '8000:8000',
      status: 'running',
      stack: 'compose.preview.yml',
      env: 'Preview',
      hostId: 'host-1',
    },
  ]
    : []

  return {
    issues,
    pullRequests,
    commits,
    workflows,
    workflowRuns,
    canvases,
    docs,
    mindMaps,
    tables,
    dbConn: d.dbConn,
    sqlDefault: d.sqlDefault,
    migrations: [{ name: '001_init.sql', status: 'applied' }, { name: '002_metrics.sql', status: 'applied' }],
    jobs,
    agents,
    httpTools,
    mcps,
    envEntries,
    testSuites,
    lastTestRun: useDemoCatalog
      ? {
          suiteId: 'suite-1',
          status: d.tests.failedN ? 'failed' : 'passed',
          summary: d.tests.summary,
          passed: d.tests.passed,
          failedN: d.tests.failedN,
          failed: d.tests.failed,
        }
      : null,
    deployHosts,
    deploys,
    deployTimeline: useDemoCatalog ? d.deployTimeline : [],
    composeFiles: useDemoCatalog ? [...DEMO_COMPOSE_FILES] : [],
    deployRuns,
    deployServices,
  }
}

interface StudioDemoState {
  byProject: Record<string, ProjectStudioState>
  ensure: (projectId: string) => ProjectStudioState
  get: (projectId: string | null | undefined) => ProjectStudioState
  update: (projectId: string, fn: (s: ProjectStudioState) => ProjectStudioState) => void

  // Issues
  createIssue: (
    projectId: string,
    data: { title: string; body: string; labels: string[]; repoId?: string },
  ) => void
  updateIssue: (projectId: string, id: string, patch: Partial<RepoIssue>) => void
  deleteIssue: (projectId: string, id: string) => void

  // PRs
  createPr: (
    projectId: string,
    data: { title: string; body: string; base: string; head: string; repoId?: string },
  ) => void

  // Jobs
  createJob: (projectId: string, data: { title: string; type: string; schedule?: string }) => void
  killJob: (projectId: string, id: string) => void

  // Agents
  createAgent: (projectId: string, data: Omit<AgentDefinition, 'id'>) => void
  updateAgent: (projectId: string, id: string, patch: Partial<AgentDefinition>) => void

  // Tools / MCP
  createTool: (projectId: string, data: Omit<HttpToolDef, 'id'>) => void
  deleteTool: (projectId: string, id: string) => void
  createMcp: (projectId: string, data: Omit<McpServerDef, 'id'>) => void
  deleteMcp: (projectId: string, id: string) => void
  toggleTool: (projectId: string, id: string) => void
  toggleMcp: (projectId: string, id: string) => void

  // Env
  createEnvEntry: (projectId: string, data: Omit<EnvEntry, 'id' | 'revealed'>) => void
  deleteEnvEntry: (projectId: string, id: string) => void
  toggleReveal: (projectId: string, id: string) => void

  // Tests
  createSuite: (projectId: string, name: string) => void
  createTestCase: (projectId: string, suiteId: string, data: Omit<TestCase, 'id'>) => void
  runSuite: (projectId: string, suiteId: string) => void

  // Knowledge
  createCanvas: (
    projectId: string,
    data: {
      name: string
      contentMd?: string
      origin?: KnowledgeOrigin
      mime?: string
      sizeLabel?: string
      desc?: string
    },
  ) => string
  updateCanvas: (projectId: string, id: string, patch: Partial<KnowledgeCanvas>) => void
  deleteCanvas: (projectId: string, id: string) => void
  /** Upload path: creates a canvas and runs Unlimited OCR → embed demo pipeline */
  uploadToCanvas: (
    projectId: string,
    file: { name: string; mime: string; sizeLabel: string; textContent?: string },
  ) => string
  createMindMap: (projectId: string, name: string, mermaid?: string) => string
  updateMindMap: (projectId: string, id: string, patch: Partial<Pick<MindMap, 'name' | 'mermaid'>>) => void
  deleteMindMap: (projectId: string, id: string) => void
  /** @deprecated Prefer createCanvas / uploadToCanvas */
  addDoc: (projectId: string, doc: Omit<KnowledgeDoc, 'id' | 'status' | 'chunks'>) => void
  setDocStatus: (projectId: string, id: string, status: KnowledgeDoc['status'], chunks?: number) => void
  /** @deprecated Mind maps use Mermaid source */
  addMindNode: (projectId: string, mapId: string, label: string, parentId: string | null) => void

  // Deploy
  addHost: (
    projectId: string,
    data: Omit<DeployHost, 'id' | 'status' | 'cpuPct' | 'memPct' | 'lastSeen'>,
  ) => void
  updateHost: (projectId: string, id: string, patch: Partial<DeployHost>) => void
  removeHost: (projectId: string, id: string) => void
  saveDeployRun: (projectId: string, run: DeployRun) => void
  finalizeDeployRun: (
    projectId: string,
    run: DeployRun,
    opts: { url?: string; services: DeployService[] },
  ) => void

  // Workflows
  setWorkflowGraph: (
    projectId: string,
    workflowId: string,
    nodes: WorkflowDef['nodes'],
    edges: WorkflowDef['edges'],
  ) => void
  addWorkflowRun: (projectId: string, run: WorkflowRun) => void
  importN8n: (projectId: string, json: unknown) => string | null
  createBlankWorkflow: (projectId: string, name?: string) => string
  deleteWorkflow: (projectId: string, workflowId: string) => void

  // SQL demo
  runSql: (projectId: string, sql: string) => SqlResult
}

export const useStudioDemoStore = create<StudioDemoState>((set, get) => ({
  byProject: {},

  ensure: (projectId: string) => {
    const id = resolveProjectId(projectId)
    const existing = get().byProject[id]
    if (existing) {
      // Strip showcase catalog noise if this became an API project after first seed
      const p = getProject(id)
      if (p?.fromApi) {
        const cleaned = stripDemoCatalog(existing)
        if (cleaned !== existing) {
          seedCache.delete(id)
          set((s) => ({ byProject: { ...s.byProject, [id]: cleaned } }))
          return cleaned
        }
      }
      return existing
    }
    const seeded = getStableSeed(id)
    // Promote into store without allocating a new seed on every snapshot.
    set((s) => {
      if (s.byProject[id]) return s
      return { byProject: { ...s.byProject, [id]: seeded } }
    })
    return get().byProject[id] ?? seeded
  },

  get: (projectId) => {
    const id = resolveProjectId(projectId)
    // Pure read for selectors — never set(), always same reference until update().
    return get().byProject[id] ?? getStableSeed(id)
  },

  update: (projectId, fn) => {
    const id = resolveProjectId(projectId)
    const cur = get().byProject[id] ?? getStableSeed(id)
    const next = fn(cur)
    seedCache.set(id, next)
    set((s) => ({ byProject: { ...s.byProject, [id]: next } }))
  },

  createIssue: (projectId, data) => {
    get().update(projectId, (s) => {
      const number = Math.max(0, ...s.issues.map((i) => i.number)) + 1
      const issue: RepoIssue = {
        id: uid('iss'),
        number,
        title: data.title,
        body: data.body,
        status: 'open',
        labels: data.labels,
        author: 'you',
        updatedAt: 'just now',
        comments: [],
        repoId: data.repoId,
      }
      return { ...s, issues: [issue, ...s.issues] }
    })
  },

  updateIssue: (projectId, id, patch) => {
    get().update(projectId, (s) => ({
      ...s,
      issues: s.issues.map((i) => (i.id === id ? { ...i, ...patch, updatedAt: 'just now' } : i)),
    }))
  },

  deleteIssue: (projectId, id) => {
    get().update(projectId, (s) => ({ ...s, issues: s.issues.filter((i) => i.id !== id) }))
  },

  createPr: (projectId, data) => {
    get().update(projectId, (s) => {
      const number = Math.max(0, ...s.pullRequests.map((p) => p.number)) + 1
      const pr: PullRequest = {
        id: uid('pr'),
        number,
        title: data.title,
        body: data.body,
        status: 'open',
        base: data.base,
        head: data.head,
        author: 'you',
        updatedAt: 'just now',
        checks: [
          { name: 'lint', status: 'pending' },
          { name: 'unit', status: 'pending' },
        ],
        reviewStatus: 'pending',
        repoId: data.repoId,
      }
      return { ...s, pullRequests: [pr, ...s.pullRequests] }
    })
  },

  createJob: (projectId, data) => {
    get().update(projectId, (s) => {
      const job: BackgroundJob = {
        id: uid('job'),
        title: data.title,
        type: data.type,
        status: 'queued',
        progress: 'waiting',
        schedule: data.schedule,
      }
      return { ...s, jobs: [job, ...s.jobs] }
    })
    // demo promote to running
    window.setTimeout(() => {
      get().update(projectId, (s) => ({
        ...s,
        jobs: s.jobs.map((j) =>
          j.title === data.title && j.status === 'queued'
            ? { ...j, status: 'run', progress: 'step 1/3' }
            : j,
        ),
      }))
    }, 800)
  },

  killJob: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      jobs: s.jobs.map((j) =>
        j.id === id && (j.status === 'run' || j.status === 'queued')
          ? { ...j, status: 'cancelled', progress: 'killed (demo)' }
          : j,
      ),
    }))
  },

  createAgent: (projectId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      agents: [{ ...data, id: uid('agent') }, ...s.agents],
    }))
  },

  updateAgent: (projectId, id, patch) => {
    get().update(projectId, (s) => ({
      ...s,
      agents: s.agents.map((a) => (a.id === id ? { ...a, ...patch } : a)),
    }))
  },

  createTool: (projectId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      httpTools: [{ ...data, id: uid('tool') }, ...s.httpTools],
    }))
  },

  deleteTool: (projectId, id) => {
    get().update(projectId, (s) => ({ ...s, httpTools: s.httpTools.filter((t) => t.id !== id) }))
  },

  createMcp: (projectId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      mcps: [{ ...data, id: uid('mcp') }, ...s.mcps],
    }))
  },

  deleteMcp: (projectId, id) => {
    get().update(projectId, (s) => ({ ...s, mcps: s.mcps.filter((m) => m.id !== id) }))
  },

  toggleTool: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      httpTools: s.httpTools.map((t) => (t.id === id ? { ...t, on: !t.on } : t)),
    }))
  },

  toggleMcp: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      mcps: s.mcps.map((m) => (m.id === id ? { ...m, on: !m.on } : m)),
    }))
  },

  createEnvEntry: (projectId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      envEntries: [{ ...data, id: uid('env'), revealed: false }, ...s.envEntries],
    }))
  },

  deleteEnvEntry: (projectId, id) => {
    get().update(projectId, (s) => ({ ...s, envEntries: s.envEntries.filter((e) => e.id !== id) }))
  },

  toggleReveal: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      envEntries: s.envEntries.map((e) => (e.id === id ? { ...e, revealed: !e.revealed } : e)),
    }))
  },

  createSuite: (projectId, name) => {
    get().update(projectId, (s) => ({
      ...s,
      testSuites: [...s.testSuites, { id: uid('suite'), name, cases: [] }],
    }))
  },

  createTestCase: (projectId, suiteId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      testSuites: s.testSuites.map((suite) =>
        suite.id === suiteId
          ? { ...suite, cases: [...suite.cases, { ...data, id: uid('tc') }] }
          : suite,
      ),
    }))
  },

  runSuite: (projectId, suiteId) => {
    get().update(projectId, (s) => {
      const suite = s.testSuites.find((x) => x.id === suiteId)
      if (!suite) return s
      const failed = suite.cases.filter((c) => c.lastStatus === 'failed').map((c) => c.name)
      const passed = suite.cases.filter((c) => c.lastStatus !== 'failed').length
      return {
        ...s,
        lastTestRun: {
          suiteId,
          status: failed.length ? 'failed' : 'passed',
          summary: `${passed} passed · ${failed.length} failed`,
          passed,
          failedN: failed.length,
          failed,
        },
      }
    })
  },

  createCanvas: (projectId, data) => {
    const id = uid('cv')
    const canvas: KnowledgeCanvas = {
      id,
      name: data.name,
      desc: data.desc,
      contentMd:
        data.contentMd ??
        `# ${data.name}\n\nStart writing knowledge for your project chatbot here.\n`,
      origin: data.origin ?? 'created',
      // Notes-only until the user (or upload pipeline) adds to chatbot knowledge
      status: 'ready',
      chunks: undefined,
      mime: data.mime,
      sizeLabel: data.sizeLabel,
      updatedAt: 'just now',
    }
    get().update(projectId, (s) => ({
      ...s,
      canvases: [canvas, ...s.canvases],
    }))
    return id
  },

  updateCanvas: (projectId, id, patch) => {
    get().update(projectId, (s) => ({
      ...s,
      canvases: s.canvases.map((c) =>
        c.id === id ? { ...c, ...patch, updatedAt: 'just now' } : c,
      ),
    }))
  },

  deleteCanvas: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      canvases: s.canvases.filter((c) => c.id !== id),
    }))
  },

  uploadToCanvas: (projectId, file) => {
    const isPdf =
      file.mime === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    const id = uid('cv')
    const origin: KnowledgeOrigin = isPdf ? 'ocr' : 'upload'
    const initialMd =
      file.textContent ||
      (isPdf
        ? `# ${file.name.replace(/\.pdf$/i, '')}\n\n> Converted from PDF via **Unlimited OCR** (demo).\n\n## Extracted content\n\nPage 1 of **${file.name}** was converted to Markdown for embedding.\n\n- Heading and body text preserved\n- Tables flattened to lists where needed\n- Ready for chunk → embed → vector store\n`
        : `# ${file.name}\n\nUploaded knowledge document.\n`)

    const canvas: KnowledgeCanvas = {
      id,
      name: file.name,
      desc: isPdf ? 'Unlimited OCR conversion' : 'Uploaded document',
      contentMd: isPdf ? '' : initialMd,
      origin,
      status: 'uploading',
      chunks: 0,
      mime: file.mime,
      sizeLabel: file.sizeLabel,
      updatedAt: 'just now',
    }
    get().update(projectId, (s) => ({
      ...s,
      canvases: [canvas, ...s.canvases],
    }))

    const schedule = (
      delay: number,
      status: EmbedStatus,
      patch?: Partial<KnowledgeCanvas>,
    ) => {
      window.setTimeout(() => {
        get().updateCanvas(projectId, id, { status, ...patch })
      }, delay)
    }

    if (isPdf) {
      // Unlimited OCR → Markdown only; chatbot indexing is a separate optional step
      schedule(600, 'ocr')
      schedule(1400, 'ocr', { contentMd: initialMd })
      schedule(2200, 'ready', { contentMd: initialMd, chunks: undefined })
    } else {
      // Text/Markdown land as notes-only immediately
      schedule(400, 'ready', { contentMd: initialMd, chunks: undefined })
    }

    return id
  },

  createMindMap: (projectId, name, mermaid) => {
    const id = uid('mm')
    const source =
      mermaid ??
      `mindmap
  root((${name.replace(/[()]/g, '')}))
    Topic A
      Detail
    Topic B`
    get().update(projectId, (s) => ({
      ...s,
      mindMaps: [
        { id, name, mermaid: source, updatedAt: 'just now' },
        ...s.mindMaps,
      ],
    }))
    return id
  },

  updateMindMap: (projectId, id, patch) => {
    get().update(projectId, (s) => ({
      ...s,
      mindMaps: s.mindMaps.map((m) =>
        m.id === id ? { ...m, ...patch, updatedAt: 'just now' } : m,
      ),
    }))
  },

  deleteMindMap: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      mindMaps: s.mindMaps.filter((m) => m.id !== id),
    }))
  },

  addDoc: (projectId, doc) => {
    get().uploadToCanvas(projectId, {
      name: doc.name,
      mime: doc.mime,
      sizeLabel: doc.sizeLabel,
    })
  },

  setDocStatus: (projectId, id, status, chunks) => {
    // Legacy: treat id as canvas id when present
    get().updateCanvas(projectId, id, {
      status,
      chunks: chunks,
    })
  },

  addMindNode: (projectId, mapId, label, parentId) => {
    // Legacy path: append a note line into mermaid source
    void parentId
    get().update(projectId, (s) => ({
      ...s,
      mindMaps: s.mindMaps.map((m) => {
        if (m.id !== mapId) return m
        const indent = '      '
        return {
          ...m,
          mermaid: `${(m.mermaid || '').trimEnd()}\n${indent}${label}`,
          updatedAt: 'just now',
          nodes: m.nodes,
        }
      }),
    }))
  },

  addHost: (projectId, data) => {
    get().update(projectId, (s) => ({
      ...s,
      deployHosts: [
        ...s.deployHosts,
        {
          ...data,
          id: uid('host'),
          status: 'online',
          lastSeen: 'just now',
          orchestrator: data.orchestrator ?? 'podman-compose',
          cpuPct: 10 + Math.floor(Math.random() * 30),
          memPct: 20 + Math.floor(Math.random() * 40),
        },
      ],
    }))
  },

  updateHost: (projectId, id, patch) => {
    get().update(projectId, (s) => ({
      ...s,
      deployHosts: s.deployHosts.map((h) => (h.id === id ? { ...h, ...patch } : h)),
    }))
  },

  removeHost: (projectId, id) => {
    get().update(projectId, (s) => ({
      ...s,
      deployHosts: s.deployHosts.filter((h) => h.id !== id),
      deployServices: s.deployServices.filter((svc) => svc.hostId !== id),
    }))
  },

  saveDeployRun: (projectId, run) => {
    get().update(projectId, (s) => {
      const exists = s.deployRuns.some((r) => r.id === run.id)
      return {
        ...s,
        deployRuns: exists
          ? s.deployRuns.map((r) => (r.id === run.id ? run : r))
          : [run, ...s.deployRuns],
      }
    })
  },

  finalizeDeployRun: (projectId, run, opts) => {
    get().update(projectId, (s) => {
      const host = s.deployHosts.find((h) => h.id === run.hostId)
      const rec: DeployRecord | null =
        run.status === 'ok' && run.action !== 'validate'
          ? {
              id: uid('dep'),
              env: run.env,
              url:
                opts.url ??
                `https://${run.env.toLowerCase()}.${host?.name ?? 'host'}.local`,
              status: run.action === 'down' ? 'stopped' : 'ok',
              when: 'Just now',
              hostId: run.hostId,
              composeFile: run.composeFile,
              runId: run.id,
            }
          : null

      let services = s.deployServices
      if (run.action === 'down' && run.status === 'ok') {
        services = s.deployServices.map((svc) =>
          svc.hostId === run.hostId && svc.env === run.env
            ? { ...svc, status: 'stopped' as const }
            : svc,
        )
      } else if (opts.services.length > 0) {
        // replace stack services for this host+env
        services = [
          ...opts.services,
          ...s.deployServices.filter(
            (svc) => !(svc.hostId === run.hostId && svc.env === run.env),
          ),
        ]
      }

      const exists = s.deployRuns.some((r) => r.id === run.id)
      return {
        ...s,
        deployRuns: exists
          ? s.deployRuns.map((r) => (r.id === run.id ? run : r))
          : [run, ...s.deployRuns],
        deploys: rec ? [rec, ...s.deploys.filter((d) => !(d.env === run.env && d.hostId === run.hostId))] : s.deploys,
        deployServices: services,
        deployTimeline: [
          {
            time: 'Just now',
            msg: `${run.action} · ${run.env} · ${run.composeFile} on ${host?.name ?? run.hostId} → ${run.status}`,
          },
          ...s.deployTimeline,
        ],
      }
    })
  },

  setWorkflowGraph: (projectId, workflowId, nodes, edges) => {
    get().update(projectId, (s) => ({
      ...s,
      workflows: s.workflows.map((w) => (w.id === workflowId ? { ...w, nodes, edges } : w)),
    }))
  },

  addWorkflowRun: (projectId, run) => {
    get().update(projectId, (s) => ({
      ...s,
      workflowRuns: [run, ...s.workflowRuns],
      workflows: s.workflows.map((w) =>
        w.id === run.workflowId ? { ...w, runs: w.runs + 1 } : w,
      ),
    }))
  },

  createBlankWorkflow: (projectId, name) => {
    const id = uid('wf')
    const nodeId = `n-${Date.now()}`
    get().update(projectId, (s) => ({
      ...s,
      workflows: [
        {
          id,
          name: name?.trim() || 'Untitled workflow',
          status: 'idle',
          trigger: 'manual',
          runs: 0,
          active: false,
          nodes: [
            {
              id: nodeId,
              type: 'studio',
              position: { x: 240, y: 300 },
              data: {
                label: 'Start',
                kind: 'trigger' as WfNodeKind,
                n8nType: 'n8n-nodes-base.manualTrigger',
                typeVersion: 1,
                category: 'trigger',
                supported: true,
                parameters: {},
              },
            },
          ],
          edges: [],
          n8nDocument: {
            name: name?.trim() || 'Untitled workflow',
            nodes: [
              {
                id: nodeId,
                name: 'Start',
                type: 'n8n-nodes-base.manualTrigger',
                typeVersion: 1,
                position: [240, 300],
                parameters: {},
              },
            ],
            connections: {},
          },
        },
        ...s.workflows,
      ],
    }))
    return id
  },

  deleteWorkflow: (projectId, workflowId) => {
    get().update(projectId, (s) => ({
      ...s,
      workflows: s.workflows.filter((w) => w.id !== workflowId),
      workflowRuns: s.workflowRuns.filter((r) => r.workflowId !== workflowId),
    }))
  },

  importN8n: (projectId, json) => {
    try {
      const derived = deriveN8nGraph(json)
      const nodes: WorkflowDef['nodes'] = derived.nodes.map((n) => ({
        id: n.id,
        type: 'studio',
        position: n.position,
        data: {
          label: n.name,
          kind: categoryToLegacyKind(n.category) as WfNodeKind,
          n8nType: n.type,
          typeVersion: n.typeVersion,
          category: n.category,
          supported: n.supported,
          parameters: n.parameters,
          credentials: n.credentials,
          params: { n8nType: n.type },
          disabled: n.disabled,
          retryOnFail: n.retryOnFail,
          maxTries: n.maxTries,
        },
      }))
      const edges: WorkflowDef['edges'] = derived.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        connectionType: e.connectionType,
        sourceHandle: e.sourceHandle,
        sourceIndex: e.sourceIndex,
        targetIndex: e.targetIndex,
      }))
      const id = uid('wf')
      const doc =
        json && typeof json === 'object' ? (json as Record<string, unknown>) : {}
      get().update(projectId, (s) => ({
        ...s,
        workflows: [
          {
            id,
            name: derived.name,
            status: 'idle',
            trigger: derived.report.triggerSummary,
            runs: 0,
            nodes,
            edges,
            n8nDocument: doc,
            importReport: derived.report as unknown as Record<string, unknown>,
            active: derived.active,
          },
          ...s.workflows,
        ],
      }))
      return id
    } catch {
      return null
    }
  },

  runSql: (projectId, sql) => {
    const s = get().ensure(projectId)
    const q = sql.trim().toLowerCase()
    if (!q) return { columns: [], rows: [], error: 'Empty query' }
    if (q.includes('error') || q.includes('drop ')) {
      return { columns: [], rows: [], error: 'Demo engine refused query (simulated error)' }
    }
    const table = s.tables.find((t) => q.includes(t.name.toLowerCase()))
    if (table) {
      const cols = table.columns ?? ['col']
      const rows = Array.from({ length: Math.min(5, table.rows) }, (_, i) =>
        cols.map((_c, j) => (j === 0 ? `${table.name}_${i + 1}` : String((i + 1) * (j + 3)))),
      )
      return { columns: cols, rows, rowCount: rows.length }
    }
    // default sample from studioExtras shape
    const extras = getStudioExtras(projectId)
    if (extras.sqlRows.length) {
      return {
        columns: extras.sqlRows[0].map((_, i) => `c${i + 1}`),
        rows: extras.sqlRows,
        rowCount: extras.sqlRows.length,
      }
    }
    return { columns: ['result'], rows: [['ok']], rowCount: 1 }
  },
}))

/**
 * Safe React subscription for project studio state.
 * Selects a stable byProject entry (or cached seed) and ensures the project is in the store once.
 */
export function useProjectStudio(projectId: string | null | undefined): ProjectStudioState {
  const id = resolveProjectId(projectId)
  const state = useStudioDemoStore((s) => s.byProject[id] ?? s.get(id))
  const ensure = useStudioDemoStore((s) => s.ensure)

  useEffect(() => {
    ensure(id)
  }, [id, ensure])

  return state
}
