import { CHAT_AGENTS, DEFAULT_CHAT_MODE, DEFAULT_CONTEXT_WINDOW } from '@/data/chatCatalog'
import type { ChatConversation, ChatMessage } from '@/types/panels'

const agents = {
  planner: CHAT_AGENTS.find((a) => a.id === 'planner')!,
  architect: CHAT_AGENTS.find((a) => a.id === 'architect')!,
  frontend: CHAT_AGENTS.find((a) => a.id === 'frontend')!,
  backend: CHAT_AGENTS.find((a) => a.id === 'backend')!,
}

/** Demo SVG as data URL for image block showcase */
const DEMO_CHART_SVG =
  'data:image/svg+xml,' +
  encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="480" height="200" viewBox="0 0 480 200">
  <rect width="480" height="200" fill="#1a1a2e"/>
  <text x="24" y="32" fill="#a0aec0" font-family="system-ui" font-size="14">Memory pressure (demo)</text>
  <polyline fill="none" stroke="#3b82f6" stroke-width="3" points="24,160 80,140 140,120 200,90 260,100 320,70 380,55 440,40"/>
  <line x1="24" y1="110" x2="440" y2="110" stroke="#f59e0b" stroke-dasharray="6 4"/>
  <text x="350" y="105" fill="#f59e0b" font-family="system-ui" font-size="11">65% warn</text>
</svg>`)

export function defaultMetrics(used = 4200): ChatConversation['metrics'] {
  return {
    contextUsedTokens: used,
    contextWindowTokens: DEFAULT_CONTEXT_WINDOW,
    tokensPerSec: 42,
    ttftMs: 180,
  }
}

export function buildShowcaseConversation(): ChatConversation {
  const messages: ChatMessage[] = [
    {
      id: 'm1',
      role: 'user',
      text: 'The MetricCard status ring is wrong at 67% memory. Also search how others threshold warnings, and attach the design notes.',
      blocks: [
        {
          type: 'text',
          text: 'The MetricCard status ring is wrong at 67% memory. Also search how others threshold warnings, and attach the design notes.',
        },
        {
          type: 'attachment',
          attachment: {
            id: 'att1',
            name: 'metric-card-notes.md',
            mime: 'text/markdown',
            sizeLabel: '4.2 KB',
            kind: 'file',
          },
        },
        {
          type: 'image',
          imageUrl: DEMO_CHART_SVG,
          alt: 'Memory pressure chart screenshot',
        },
      ],
      createdAt: new Date(Date.now() - 120_000).toISOString(),
    },
    {
      id: 'm2',
      role: 'assistant',
      agent: agents.planner,
      thinking: 'Scoping: UI threshold bug + research + multi-agent plan.',
      blocks: [
        {
          type: 'markdown',
          text: `## Plan

I'll split this across agents:

1. **Architect** — confirm threshold model
2. **Backend** — optional API status field
3. **Frontend** — fix \`MetricCard\` ring mapping

### Acceptance

| Case | Expected |
|------|----------|
| 64% | healthy |
| 67% | **warning** |
| 91% | critical |`,
        },
        {
          type: 'question',
          text: 'Which approach should we use for thresholds?',
          options: [
            'Client-only (≥65 warn, ≥90 critical)',
            'API returns status enum',
            'Both — API source of truth + client fallback',
          ],
        },
      ],
      metrics: { ttftMs: 210, tokensPerSec: 48, completionTokens: 186 },
      createdAt: new Date(Date.now() - 110_000).toISOString(),
    },
    {
      id: 'm3',
      role: 'user',
      text: 'Client-only (≥65 warn, ≥90 critical)',
      createdAt: new Date(Date.now() - 100_000).toISOString(),
    },
    {
      id: 'm4',
      role: 'assistant',
      agent: agents.architect,
      blocks: [
        {
          type: 'web_search',
          webSearch: {
            query: 'dashboard metric card warning threshold memory percentage UX',
            results: [
              {
                title: 'Nielsen Norman — Status indicators',
                url: 'https://www.nngroup.com/articles/status-indicators/',
                snippet: 'Use caution states before critical; avoid binary healthy/critical only.',
              },
              {
                title: 'Prometheus alerting best practices',
                url: 'https://prometheus.io/docs/practices/alerting/',
                snippet: 'Separate warning and critical burn rates; give operators reaction time.',
              },
              {
                title: 'PatternFly — Alert variants',
                url: 'https://www.patternfly.org/components/alert',
                snippet: 'info / warning / danger map cleanly to healthy / warn / critical.',
              },
            ],
          },
        },
        {
          type: 'markdown',
          text: `Research backs a **three-band** model. Recommend:

\`\`\`ts
pct >= 90 → critical
pct >= 65 → warning
else → healthy
\`\`\`

Frontend owns the mapping for now.`,
        },
      ],
      metrics: { ttftMs: 320, tokensPerSec: 39, completionTokens: 240 },
      createdAt: new Date(Date.now() - 90_000).toISOString(),
    },
    {
      id: 'm5',
      role: 'assistant',
      agent: agents.backend,
      blocks: [
        {
          type: 'terminal',
          terminal: {
            command: 'rg -n "status|percentage" src/components/dashboard/MetricCard.tsx',
            output: `12:  percentage: number;\n18:  const status = pct < 80 ? "healthy" : "critical";`,
            exitCode: 0,
          },
        },
        {
          type: 'markdown',
          text: 'No API change required for client-only thresholds. Sandbox confirms the binary branch in `MetricCard.tsx`.',
        },
      ],
      metrics: { ttftMs: 140, tokensPerSec: 55, completionTokens: 92 },
      createdAt: new Date(Date.now() - 70_000).toISOString(),
    },
    {
      id: 'm6',
      role: 'assistant',
      agent: agents.frontend,
      thinking: 'Applying threshold fix in MetricCard.',
      text: 'Updated thresholds: ≥65% → warning, ≥90% → critical. Diff is in Repository → Changes.',
      blocks: [
        {
          type: 'markdown',
          text: 'Updated thresholds: **≥65% → warning**, **≥90% → critical**. Diff is in Repository → Changes.',
        },
        {
          type: 'tool',
          tool: {
            title: 'sandbox_str_replace · MetricCard.tsx',
            body: `-  const status = pct < 80 ? "healthy" : "critical";\n+  const status =\n+    pct >= 90 ? "critical" :\n+    pct >= 65 ? "warning" : "healthy";`,
            status: 'done',
          },
        },
        {
          type: 'image',
          imageUrl: DEMO_CHART_SVG,
          alt: 'Updated ring preview',
        },
      ],
      tool: {
        title: 'sandbox_str_replace · MetricCard.tsx',
        body: `-  const status = pct < 80 ? "healthy" : "critical";\n+  const status =\n+    pct >= 90 ? "critical" :\n+    pct >= 65 ? "warning" : "healthy";`,
      },
      metrics: { ttftMs: 165, tokensPerSec: 51, completionTokens: 128 },
      createdAt: new Date(Date.now() - 40_000).toISOString(),
    },
  ]

  return {
    id: 'c1',
    title: 'Fix MetricCard status ring',
    meta: 'Active · 2m ago',
    pinned: true,
    agents: [agents.planner, agents.architect, agents.frontend, agents.backend],
    primaryAgent: 'build',
    messages,
    metrics: defaultMetrics(12_400),
    chatMode: 'auto',
  }
}

export function simpleConversation(
  id: string,
  title: string,
  meta: string,
  messages: ChatMessage[],
  opts?: Partial<ChatConversation>,
): ChatConversation {
  return {
    id,
    title,
    meta,
    pinned: false,
    agents: [agents.frontend, agents.backend],
    primaryAgent: 'build',
    messages: messages.map((m, i) => ({
      ...m,
      id: m.id || `${id}_m${i + 1}`,
    })),
    metrics: defaultMetrics(Math.max(800, messages.length * 400)),
    chatMode: DEFAULT_CHAT_MODE,
    ...opts,
  }
}

export function seedConversationsForProject(
  projectId: string,
  convs: { id: string; title: string; meta: string; pinned?: boolean }[],
  primaryMessages: ChatMessage[],
): ChatConversation[] {
  if (projectId === 'aura') {
    return [
      buildShowcaseConversation(),
      simpleConversation(
        'c2',
        'Wire nginx health checks',
        'Yesterday',
        [
          {
            id: 'c2_m1',
            role: 'user',
            text: 'Add nginx health checks that hit /healthz every 10s.',
          },
          {
            id: 'c2_m2',
            role: 'assistant',
            agent: agents.backend,
            text: 'Drafted a health check sidecar config. Open Terminal to apply in the sandbox.',
            blocks: [
              {
                type: 'terminal',
                terminal: {
                  command: 'curl -sS http://localhost:8080/healthz',
                  output: '{"status":"ok","uptime":3842}',
                  exitCode: 0,
                },
              },
            ],
          },
        ],
      ),
      simpleConversation(
        'c3',
        'Deploy postgres-db scaling',
        '3 days ago',
        [
          {
            id: 'c3_m1',
            role: 'user',
            text: 'Scale postgres-db to 2 replicas for staging.',
          },
        ],
        { pinned: false },
      ),
    ]
  }

  return convs.map((c, idx) =>
    simpleConversation(
      c.id,
      c.title,
      c.meta,
      idx === 0
        ? primaryMessages.map((m, i) => ({
            ...m,
            id: m.id || `${c.id}_m${i + 1}`,
          }))
        : [],
      { pinned: !!c.pinned },
    ),
  )
}
