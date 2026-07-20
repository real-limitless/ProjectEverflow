export interface HarnessDef {
  id: string
  name: string
  description: string
  category: 'ci' | 'runtime' | 'data' | 'ai' | 'deploy'
}

export const HARNESS_CATALOG: HarnessDef[] = [
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
    description: 'Managed Postgres for the Database panel and migrations.',
    category: 'data',
  },
]

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
