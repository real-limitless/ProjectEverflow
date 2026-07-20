/** Shared studio demo types for panel overhauls (demo-local, not platform API). */

export type JobStatus = 'run' | 'queued' | 'ok' | 'err' | 'cancelled'
export type IssueStatus = 'open' | 'closed'
export type PrStatus = 'open' | 'merged' | 'draft' | 'closed'
export type EmbedStatus = 'uploading' | 'chunking' | 'embedding' | 'indexed' | 'error'
export type TestCaseType = 'unit' | 'e2e' | 'smoke'
export type TestRunStatus = 'idle' | 'running' | 'passed' | 'failed'
export type DeployHostStatus = 'online' | 'offline' | 'unknown'
export type PipelineStageStatus = 'pending' | 'running' | 'ok' | 'err' | 'skipped'

export interface RepoIssueComment {
  id: string
  author: string
  body: string
  createdAt: string
}

export interface RepoIssue {
  id: string
  number: number
  title: string
  body: string
  status: IssueStatus
  labels: string[]
  author: string
  updatedAt: string
  comments: RepoIssueComment[]
}

export interface PullRequest {
  id: string
  number: number
  title: string
  body: string
  status: PrStatus
  base: string
  head: string
  author: string
  updatedAt: string
  checks: { name: string; status: 'ok' | 'pending' | 'fail' }[]
  reviewStatus: 'approved' | 'changes_requested' | 'pending'
}

export interface GitCommit {
  id: string
  hash: string
  shortHash: string
  message: string
  author: string
  when: string
  parents: string[]
  branchLabels: string[]
  files: string[]
  isHead?: boolean
}

export interface GitGraphLane {
  commitId: string
  lane: number
  branch?: string
}

export interface TerminalLine {
  cls: string
  text: string
}

export interface TerminalSession {
  id: string
  name: string
  lines: TerminalLine[]
  history: string[]
}

export type WfNodeKind = 'trigger' | 'http' | 'llm' | 'code' | 'condition' | 'notify' | 'unknown'

export interface WfNodeData extends Record<string, unknown> {
  label: string
  kind: WfNodeKind
  params?: Record<string, string>
  running?: boolean
}

export interface WorkflowDef {
  id: string
  name: string
  status: string
  trigger: string
  runs: number
  nodes: { id: string; type: string; position: { x: number; y: number }; data: WfNodeData }[]
  edges: { id: string; source: string; target: string }[]
}

export interface WorkflowRun {
  id: string
  workflowId: string
  status: string
  dur: string
  when: string
  log: string[]
}

export interface KnowledgeDoc {
  id: string
  name: string
  mime: string
  sizeLabel: string
  status: EmbedStatus
  chunks?: number
  canvasId?: string
}

export interface KnowledgeCanvas {
  id: string
  name: string
  desc: string
  docIds: string[]
}

export interface WebSearchHit {
  id: string
  title: string
  url: string
  snippet: string
}

export interface MindMapNode {
  id: string
  label: string
  parentId: string | null
}

export interface MindMap {
  id: string
  name: string
  nodes: MindMapNode[]
}

export interface DbTable {
  name: string
  rows: number
  size: string
  columns?: string[]
}

export interface SqlResult {
  columns: string[]
  rows: string[][]
  error?: string
  rowCount?: number
}

export interface BackgroundJob {
  id: string
  title: string
  type: string
  status: JobStatus
  progress: string
  schedule?: string
}

export interface AgentDefinition {
  id: string
  name: string
  role: string
  desc: string
  systemPrompt: string
  tools: string[]
  active: boolean
}

export interface HttpToolDef {
  id: string
  name: string
  method: string
  url: string
  headers?: string
  on: boolean
}

export interface McpServerDef {
  id: string
  name: string
  transport: string
  endpoint: string
  on: boolean
}

export interface EnvEntry {
  id: string
  key: string
  value: string
  kind: 'env' | 'secret'
  attachedTo?: string[]
  revealed?: boolean
}

export interface TestCase {
  id: string
  name: string
  type: TestCaseType
  command: string
  lastStatus?: 'passed' | 'failed' | 'skipped'
  error?: string
}

export interface TestSuite {
  id: string
  name: string
  cases: TestCase[]
}

export interface TestRunSummary {
  suiteId: string
  status: TestRunStatus
  summary: string
  passed: number
  failedN: number
  failed: string[]
}

export type DeployAction = 'up' | 'down' | 'validate' | 'redeploy'
export type DeployRunStatus = 'running' | 'ok' | 'err' | 'cancelled'
export type DeployServiceStatus = 'running' | 'stopped' | 'restarting'

export interface DeployHost {
  id: string
  name: string
  host: string
  status: DeployHostStatus
  user?: string
  port?: number
  tags?: string[]
  lastSeen?: string
  orchestrator?: 'podman-compose' | 'docker-compose'
  cpuPct?: number
  memPct?: number
}

export interface DeployPipelineStage {
  id: string
  name: string
  status: PipelineStageStatus
  log?: string
}

export interface DeployRecord {
  id: string
  env: string
  url: string
  status: string
  when: string
  hostId?: string
  composeFile?: string
  runId?: string
}

export interface DeployRun {
  id: string
  hostId: string
  env: string
  composeFile: string
  action: DeployAction
  status: DeployRunStatus
  startedAt: string
  finishedAt?: string
  durationLabel?: string
  stages: DeployPipelineStage[]
  logLines: string[]
  attachedEnvIds: string[]
}

export interface DeployService {
  id: string
  name: string
  image: string
  ports: string
  status: DeployServiceStatus
  stack: string
  env: string
  hostId: string
}

export interface ProjectStudioState {
  issues: RepoIssue[]
  pullRequests: PullRequest[]
  commits: GitCommit[]
  workflows: WorkflowDef[]
  workflowRuns: WorkflowRun[]
  canvases: KnowledgeCanvas[]
  docs: KnowledgeDoc[]
  mindMaps: MindMap[]
  tables: DbTable[]
  dbConn: string
  sqlDefault: string
  migrations: { name: string; status: string }[]
  jobs: BackgroundJob[]
  agents: AgentDefinition[]
  httpTools: HttpToolDef[]
  mcps: McpServerDef[]
  envEntries: EnvEntry[]
  testSuites: TestSuite[]
  lastTestRun: TestRunSummary | null
  deployHosts: DeployHost[]
  deploys: DeployRecord[]
  deployTimeline: { time: string; msg: string }[]
  composeFiles: string[]
  deployRuns: DeployRun[]
  deployServices: DeployService[]
}
