/** Shared studio demo types for panel overhauls (demo-local, not platform API). */

export type JobStatus = 'run' | 'queued' | 'ok' | 'err' | 'cancelled'
export type IssueStatus = 'open' | 'closed'
export type PrStatus = 'open' | 'merged' | 'draft' | 'closed'
/** Knowledge canvas pipeline / chat-readiness status */
export type EmbedStatus =
  | 'ready' // saved notes; not in chatbot vector knowledge yet
  | 'uploading'
  | 'ocr'
  | 'chunking'
  | 'embedding'
  | 'indexed' // available to chatbot retrieval
  | 'stale' // was indexed; content changed — needs re-index
  | 'error'

export type KnowledgeOrigin = 'created' | 'upload' | 'ocr' | 'web'
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
  /** Scopes demo issues to a project repository when multi-repo. */
  repoId?: string
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
  /** Scopes demo PRs to a project repository when multi-repo. */
  repoId?: string
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
  /** Scopes demo commits to a project repository when multi-repo. */
  repoId?: string
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

export type WfNodeKind =
  | 'trigger'
  | 'http'
  | 'llm'
  | 'code'
  | 'condition'
  | 'notify'
  | 'unknown'
  // n8n category aliases (canvas styling)
  | 'input'
  | 'transform'
  | 'logic'
  | 'ai'
  | 'output'
  | 'data'

export interface WfNodeData extends Record<string, unknown> {
  label: string
  kind: WfNodeKind
  /** n8n type string e.g. n8n-nodes-base.ftp */
  n8nType?: string
  typeVersion?: number | null
  category?: string
  supported?: boolean
  parameters?: Record<string, unknown>
  credentials?: Record<string, unknown> | null
  params?: Record<string, string>
  running?: boolean
  /** last run step status for canvas highlight */
  runStatus?: 'ok' | 'err' | 'running' | null
  disabled?: boolean
  retryOnFail?: boolean
  maxTries?: number | null
}

export interface WorkflowEdgeDef {
  id: string
  source: string
  target: string
  connectionType?: string
  sourceHandle?: string
  sourceIndex?: number
  targetIndex?: number
}

export interface WorkflowDef {
  id: string
  name: string
  status: string
  trigger: string
  runs: number
  nodes: { id: string; type: string; position: { x: number; y: number }; data: WfNodeData }[]
  edges: WorkflowEdgeDef[]
  /** Full n8n export when available (API / faithful import) */
  n8nDocument?: Record<string, unknown>
  importReport?: Record<string, unknown>
  active?: boolean
  /** API-backed workflow id equals id when from server */
  fromApi?: boolean
}

export interface WorkflowRun {
  id: string
  workflowId: string
  status: string
  dur: string
  when: string
  log: string[]
}

/** @deprecated Prefer KnowledgeCanvas as the knowledge document unit */
export interface KnowledgeDoc {
  id: string
  name: string
  mime: string
  sizeLabel: string
  status: EmbedStatus
  chunks?: number
  canvasId?: string
}

/** Knowledge document: Markdown body for LLM / embedding use */
export interface KnowledgeCanvas {
  id: string
  name: string
  desc?: string
  /** Markdown knowledge body */
  contentMd: string
  origin: KnowledgeOrigin
  status: EmbedStatus
  chunks?: number
  mime?: string
  sizeLabel?: string
  updatedAt?: string
}

export interface WebSearchHit {
  id: string
  title: string
  url: string
  snippet: string
  /** Cleaned full-page text for Reader mode (Markdown) */
  readerMarkdown?: string
}

/** @deprecated Mind maps are Mermaid-sourced now */
export interface MindMapNode {
  id: string
  label: string
  parentId: string | null
}

export interface MindMap {
  id: string
  name: string
  /** Mermaid diagram source (mindmap, flowchart, etc.) */
  mermaid: string
  updatedAt?: string
  /** @deprecated Prefer mermaid source */
  nodes?: MindMapNode[]
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

/** Permission action for OpenCode tools / MCP / skills. */
export type AgentPermissionAction = 'allow' | 'ask' | 'deny'

export type AgentMode = 'primary' | 'subagent' | 'all'

/**
 * Project agent definition — OpenCode-aligned (prompt + model + permissions).
 * Legacy fields (role, desc, systemPrompt, tools, active) kept for demo seed mapping.
 */
export interface AgentDefinition {
  id: string
  name: string
  /** @deprecated Prefer description; kept for demo seeds */
  role?: string
  /** Short description (OpenCode required) */
  description?: string
  /** @deprecated Prefer description */
  desc?: string
  /** Instruction prompt body */
  prompt?: string
  /** @deprecated Prefer prompt */
  systemPrompt?: string
  mode?: AgentMode
  /** Primary model id: provider/model */
  model?: string
  /** Preferred models for Chat picker (Everflow metadata; only model written to OpenCode) */
  modelsPreferred?: string[]
  permission?: Record<string, AgentPermissionAction | Record<string, AgentPermissionAction>>
  /** MCP server names this agent may use */
  mcpIds?: string[]
  /** Skill names/patterns allowed */
  skillAllow?: string[]
  color?: string
  temperature?: number
  disable?: boolean
  managed?: boolean
  source?: 'opencode-builtin' | 'opencode-file' | 'everflow' | 'demo'
  /** @deprecated Free-text tool names from demo form */
  tools?: string[]
  active?: boolean
}

export interface SkillDefinition {
  id: string
  name: string
  description: string
  body: string
  managed?: boolean
  source?: 'opencode-file' | 'everflow' | 'demo'
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
  /** OpenCode MCP config blob when synced */
  config?: Record<string, unknown>
  status?: string
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
