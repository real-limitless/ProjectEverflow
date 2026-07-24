/** Map platform API studio resources ↔ UI studio types. */

import type {
  ApiKnowledgeCanvas,
  ApiProjectAgent,
  ApiTestCase,
  ApiTestSuite,
  ApiTestSuiteRunResult,
} from '@/lib/api'
import type {
  AgentDefinition,
  KnowledgeCanvas,
  TestCase,
  TestCaseType,
  TestRunSummary,
  TestSuite,
} from '@/types/studio'

export function mapApiCanvas(c: ApiKnowledgeCanvas): KnowledgeCanvas {
  return {
    id: c.id,
    name: c.name,
    desc: c.description ?? undefined,
    contentMd: c.content_md ?? '',
    origin: (c.origin as KnowledgeCanvas['origin']) || 'created',
    status: (c.status as KnowledgeCanvas['status']) || 'ready',
    chunks: c.chunks ?? undefined,
    mime: c.mime ?? undefined,
    sizeLabel: c.size_label ?? undefined,
    updatedAt: c.updated_at,
    collectionId: c.collection_id ?? undefined,
    sourceUrl: c.source_url ?? undefined,
    contentHash: c.content_hash ?? undefined,
    lastFetchedAt: c.last_fetched_at ?? undefined,
    repoPath: c.repo_path ?? undefined,
  }
}

export function mapApiAgent(a: ApiProjectAgent): AgentDefinition {
  return {
    id: a.id,
    name: a.name,
    role: a.role,
    desc: a.description,
    description: a.description,
    systemPrompt: a.system_prompt,
    prompt: a.system_prompt,
    tools: a.tools || [],
    active: a.active,
    source: 'everflow',
    managed: true,
  }
}

function mapCaseStatus(status: string | null | undefined): TestCase['lastStatus'] {
  if (status === 'passed' || status === 'failed' || status === 'skipped') return status
  return undefined
}

export function mapApiTestCase(c: ApiTestCase): TestCase {
  const type = (c.type === 'e2e' || c.type === 'smoke' ? c.type : 'unit') as TestCaseType
  return {
    id: c.id,
    name: c.name,
    type,
    command: c.command || '',
    lastStatus: mapCaseStatus(c.last_status),
    error: c.last_error ?? undefined,
  }
}

export function mapApiTestSuite(s: ApiTestSuite): TestSuite {
  return {
    id: s.id,
    name: s.name,
    cases: (s.cases || []).map(mapApiTestCase),
  }
}

export function mapApiTestRun(r: ApiTestSuiteRunResult): TestRunSummary {
  const failedNames = (r.results || [])
    .filter((x) => x.status === 'failed')
    .map((x) => x.name)
  return {
    suiteId: r.suite_id,
    status: r.status,
    summary: r.summary,
    passed: r.passed,
    failedN: r.failed,
    failed: failedNames,
  }
}
