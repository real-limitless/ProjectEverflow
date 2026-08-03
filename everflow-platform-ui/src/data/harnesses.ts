export type HarnessCategory = 'ci' | 'runtime' | 'data' | 'ai' | 'deploy' | 'agent'

export interface HarnessDef {
  id: string
  name: string
  description: string
  category: HarnessCategory
}

export const HARNESS_CATEGORY_LABELS: Record<HarnessCategory, string> = {
  agent: 'Agent',
  ai: 'AI',
  ci: 'CI',
  runtime: 'Runtime',
  data: 'Data',
  deploy: 'Deploy',
}

/** Stable tab order for the Harnesses catalog page. */
export const HARNESS_CATEGORY_ORDER: HarnessCategory[] = [
  'agent',
  'ai',
  'ci',
  'runtime',
  'data',
  'deploy',
]

export const HARNESS_CATALOG: HarnessDef[] = [
  {
    id: 'agent-claude-code',
    name: 'Claude Code',
    description: 'Anthropic Claude Code CLI inside the project sandbox.',
    category: 'agent',
  },
  {
    id: 'agent-opencode',
    name: 'OpenCode',
    description: 'OpenCode agent CLI inside the project sandbox.',
    category: 'agent',
  },
  {
    id: 'ci-github',
    name: 'GitHub Actions CI',
    description: 'PR checks, lint, and unit tests on every push.',
    category: 'ci',
  },
  {
    id: 'ci-gitlab',
    name: 'GitLab CI',
    description: 'Pipeline jobs for build, test, and package.',
    category: 'ci',
  },
  {
    id: 'preview-env',
    name: 'Ephemeral preview',
    description: 'Spin up preview services for the Preview panel.',
    category: 'runtime',
  },
  {
    id: 'deploy-k8s',
    name: 'Kubernetes deploy',
    description: 'Deploy targets and rollout timeline for Deploy panel.',
    category: 'deploy',
  },
  {
    id: 'test-runner',
    name: 'Test runner',
    description: 'Sandbox test execution and result summaries.',
    category: 'ci',
  },
  {
    id: 'ai-sandbox',
    name: 'AI sandbox tools',
    description: 'Chat tools, MCP servers, and agent sandbox access.',
    category: 'ai',
  },
  {
    id: 'db-postgres',
    name: 'Postgres harness',
    description:
      'Installs psql and .everflow/database.json for the Database panel. Point DATABASE_URL at a reachable Postgres.',
    category: 'data',
  },
]

/** Default harnesses for new API-backed projects (matches backend bootstrap). */
export const DEFAULT_AGENT_HARNESS_IDS = ['agent-claude-code', 'agent-opencode'] as const

export function getHarness(id: string): HarnessDef | undefined {
  return HARNESS_CATALOG.find((h) => h.id === id)
}

export function harnessesFromIds(ids: string[]) {
  return ids
    .map((id) => {
      const def = getHarness(id)
      if (!def) return null
      return { id: def.id, label: def.name, enabled: true }
    })
    .filter(Boolean) as { id: string; label: string; enabled: boolean }[]
}

/** Enabled harness ids currently attached to a project. */
export function enabledHarnessIds(
  harnesses: { id: string; enabled: boolean }[] | undefined | null,
): string[] {
  if (!harnesses?.length) return []
  return harnesses.filter((h) => h.enabled).map((h) => h.id)
}

/** Normalize API harness payload (ids or objects) into project harness rows. */
export function harnessesFromApi(
  raw: Array<string | { id: string; label?: string; enabled?: boolean }> | null | undefined,
): { id: string; label: string; enabled: boolean }[] {
  if (!raw?.length) return []
  const ids: string[] = []
  for (const item of raw) {
    if (typeof item === 'string') {
      if (item.trim()) ids.push(item.trim())
      continue
    }
    if (item?.enabled === false) continue
    if (item?.id?.trim()) ids.push(item.id.trim())
  }
  return harnessesFromIds(listUnique(ids))
}

function listUnique(ids: string[]): string[] {
  return [...new Set(ids)]
}

/** Shell command to launch a harness CLI inside the sandbox. */
export function harnessLaunchCommand(id: string): string | null {
  if (id === 'agent-claude-code' || id === 'claude-code') return 'claude'
  if (id === 'agent-opencode' || id === 'opencode') return 'opencode'
  return null
}
