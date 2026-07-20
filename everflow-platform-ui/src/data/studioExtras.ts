import { PROJECTS } from './projects'

export interface StudioExtras {
  projectName: string
  workflows: { name: string; status: string; trigger: string; runs: number }[]
  wfNodes: { cls: string; label: string }[]
  wfRuns: { id: string; status: string; dur: string; when: string }[]
  tables: { name: string; rows: number; size: string }[]
  dbConn: string
  sqlDefault: string
  sqlRows: string[][]
  jobs: { title: string; status: string; progress: string }[]
  agents: { id: string; name: string; desc: string; active: boolean }[]
  httpTools: { name: string; method: string; on: boolean }[]
  mcps: { name: string; transport: string; on: boolean }[]
  envVars: { key: string; value: string }[]
  secrets: { key: string; value: string }[]
  tests: {
    summary: string
    failed: string[]
    passed: number
    failedN: number
  }
  deploys: { env: string; url: string; status: string; when: string }[]
  deployTimeline: { time: string; msg: string }[]
}

export function getStudioExtras(projectId: string | null | undefined): StudioExtras {
  const project =
    (projectId ? PROJECTS[projectId] : undefined) ??
    Object.values(PROJECTS)[0] ?? {
      id: 'empty',
      name: 'No project',
    }
  const id = project.id
  const name = project.name

  const base: StudioExtras = {
    projectName: name,
    workflows: [
      { name: 'On push → lint & preview', status: 'ok', trigger: 'git.push', runs: 42 },
      { name: 'Nightly metrics scrape', status: 'idle', trigger: 'cron 0 3 * * *', runs: 18 },
      { name: 'Webhook: deploy hook', status: 'ok', trigger: 'POST /hooks/wf/…', runs: 7 },
    ],
    wfNodes: [
      { cls: 'trigger', label: 'git.push' },
      { cls: 'llm', label: 'LLM triage' },
      { cls: 'code', label: 'code.python' },
      { cls: 'http', label: 'notify Slack' },
    ],
    wfRuns: [
      { id: 'r-9182', status: 'ok', dur: '12.4s', when: '2m ago' },
      { id: 'r-9181', status: 'err', dur: '3.1s', when: '1h ago' },
      { id: 'r-9170', status: 'ok', dur: '11.8s', when: 'yesterday' },
    ],
    tables: [
      { name: 'containers', rows: 6, size: '48 KB' },
      { name: 'metrics_samples', rows: 12840, size: '2.1 MB' },
      { name: 'users', rows: 3, size: '12 KB' },
    ],
    dbConn: `postgres://***@db.internal:5432/${id}`,
    sqlDefault: 'SELECT name, status, cpu FROM containers ORDER BY cpu DESC LIMIT 5;',
    sqlRows: [
      ['nginx-proxy', 'running', '12'],
      ['postgres-db', 'running', '34'],
      ['redis-cache', 'running', '5'],
      ['node-api', 'running', '45'],
      ['wordpress-site', 'stopped', '0'],
    ],
    jobs: [
      { title: 'Batch canvas export', status: 'run', progress: 'step 2/4' },
      { title: 'Repo index · shallow tree', status: 'ok', progress: 'done' },
      { title: 'PII redaction pass', status: 'queued', progress: 'waiting' },
    ],
    agents: [
      { id: 'a1', name: 'Coding Assistant', desc: 'Sandbox FS + git tools', active: true },
      { id: 'a2', name: 'General Assistant', desc: 'Chat + canvas, light tools', active: false },
      { id: 'a3', name: 'Deploy Reviewer', desc: 'Diffs + checklist only', active: false },
    ],
    httpTools: [
      { name: 'statuspage_ping', method: 'GET', on: true },
      { name: 'slack_notify', method: 'POST', on: true },
    ],
    mcps: [
      { name: 'github-mcp', transport: 'HTTP/SSE', on: true },
      { name: 'docs-search', transport: 'HTTP/SSE', on: false },
    ],
    envVars: [
      { key: 'NODE_ENV', value: 'development' },
      { key: 'VITE_API_URL', value: 'http://localhost:8000' },
      { key: 'PORT', value: '5173' },
    ],
    secrets: [
      { key: 'OPENROUTER_API_KEY', value: 'sk-or-…••••a91f' },
      { key: 'DATABASE_URL', value: 'postgres://…••••@db' },
      { key: 'STRIPE_SECRET', value: 'sk_test_…••••9c' },
    ],
    tests: {
      summary: '18 passed · 2 failed · 1 skipped',
      failed: [
        'MetricCard › warning threshold at 67%',
        'HealthCheck › redis ping timeout',
      ],
      passed: 18,
      failedN: 2,
    },
    deploys: [
      { env: 'Preview', url: `https://preview.${id}.local`, status: 'ok', when: 'Just now' },
      { env: 'Staging', url: `https://staging.${id}.local`, status: 'warn', when: '3h ago' },
    ],
    deployTimeline: [
      { time: 'Just now', msg: 'Preview build #128 — healthy' },
      { time: '3h ago', msg: 'Staging deploy — waiting smoke tests' },
      { time: 'Yesterday', msg: 'Preview build #127 — healthy' },
    ],
  }

  if (id === 'callour') {
    base.workflows = [
      { name: 'Publish landing', status: 'ok', trigger: 'manual', runs: 11 },
      { name: 'Image optimize on push', status: 'idle', trigger: 'git.push', runs: 4 },
    ]
    base.tables = [
      { name: 'leads', rows: 24, size: '32 KB' },
      { name: 'portfolio_items', rows: 8, size: '96 KB' },
    ]
    base.sqlDefault = 'SELECT name, role FROM team ORDER BY sort ASC;'
    base.sqlRows = [
      ['Ayu', 'Design lead'],
      ['Rafi', 'Engineer'],
      ['Siti', 'PM'],
    ]
    base.tests = {
      summary: '9 passed · 0 failed',
      failed: [],
      passed: 9,
      failedN: 0,
    }
    base.agents[0].name = 'Brand Coder'
  }

  if (id === 'router') {
    base.workflows = [
      { name: 'Studio job worker health', status: 'ok', trigger: 'cron */5', runs: 220 },
      { name: 'n8n import smoke', status: 'ok', trigger: 'manual', runs: 6 },
    ]
    base.mcps.push({ name: 'litellm-admin', transport: 'HTTP/SSE', on: false })
    base.jobs = [
      { title: 'workflow_run · graph v2', status: 'run', progress: 'node code.python' },
      { title: 'seed OpenRouter models', status: 'ok', progress: 'done' },
    ]
  }

  return base
}
