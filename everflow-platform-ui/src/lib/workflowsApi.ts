/**
 * Project workflows API (n8n-compatible import + CRUD).
 */

import { apiFetch } from '@/lib/api'

export interface ApiWorkflowGraphNode {
  id: string
  name: string
  type: string
  type_version?: number | null
  position: { x: number; y: number }
  parameters: Record<string, unknown>
  credentials?: Record<string, unknown> | null
  category: string
  supported: boolean
  disabled?: boolean
  retry_on_fail?: boolean
  max_tries?: number | null
  continue_on_fail?: boolean
  notes?: string | null
  webhook_id?: string | null
}

export interface ApiWorkflowGraphEdge {
  id: string
  source: string
  target: string
  source_name: string
  target_name: string
  connection_type: string
  source_index: number
  target_index: number
  source_handle: string
}

export interface ApiWorkflowGraph {
  nodes: ApiWorkflowGraphNode[]
  edges: ApiWorkflowGraphEdge[]
  name: string
  settings: Record<string, unknown>
  pin_data: Record<string, unknown>
  active: boolean
  report: Record<string, unknown>
}

export interface ApiWorkflowSummary {
  id: string
  project_id: string
  name: string
  active: boolean
  trigger_summary: string
  node_count?: number | null
  unsupported_count?: number | null
  credential_requirements_count?: number | null
  created_at: string
  updated_at: string
}

export interface ApiWorkflowRead {
  id: string
  project_id: string
  name: string
  active: boolean
  trigger_summary: string
  settings?: Record<string, unknown> | null
  credential_bindings?: Record<string, unknown> | null
  import_report?: Record<string, unknown> | null
  n8n_document: Record<string, unknown>
  graph: ApiWorkflowGraph
  created_at: string
  updated_at: string
}

export interface ApiWorkflowRun {
  id: string
  workflow_id: string
  project_id: string
  status: string
  trigger_type: string
  error_message?: string | null
  log?: unknown[] | null
  started_at: string
  finished_at?: string | null
}

export function listWorkflows(projectId: string) {
  return apiFetch<ApiWorkflowSummary[]>(`/api/v1/projects/${projectId}/workflows`)
}

export function getWorkflow(projectId: string, workflowId: string) {
  return apiFetch<ApiWorkflowRead>(`/api/v1/projects/${projectId}/workflows/${workflowId}`)
}

export function importWorkflow(
  projectId: string,
  document: unknown,
  opts?: { name?: string; active?: boolean },
) {
  const body =
    opts?.name != null || opts?.active != null
      ? { document, ...opts }
      : document
  return apiFetch<ApiWorkflowRead>(`/api/v1/projects/${projectId}/workflows/import`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateWorkflow(
  projectId: string,
  workflowId: string,
  patch: {
    name?: string
    active?: boolean
    n8n_document?: Record<string, unknown>
    credential_bindings?: Record<string, string>
  },
) {
  return apiFetch<ApiWorkflowRead>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}`,
    { method: 'PATCH', body: JSON.stringify(patch) },
  )
}

export function deleteWorkflow(projectId: string, workflowId: string) {
  return apiFetch<void>(`/api/v1/projects/${projectId}/workflows/${workflowId}`, {
    method: 'DELETE',
  })
}

export function createWorkflow(
  projectId: string,
  body: { name?: string; active?: boolean; document?: Record<string, unknown> } = {},
) {
  return apiFetch<ApiWorkflowRead>(`/api/v1/projects/${projectId}/workflows`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export interface ApiDataTableSummary {
  id: string
  project_id: string
  name: string
  columns?: unknown[] | null
  row_count: number
  created_at: string
  updated_at: string
}

export interface ApiDataTableRead extends ApiDataTableSummary {
  rows: Record<string, unknown>[]
}

export function listDataTables(projectId: string) {
  return apiFetch<ApiDataTableSummary[]>(
    `/api/v1/projects/${projectId}/workflow-data-tables`,
  )
}

export function createDataTable(
  projectId: string,
  body: { name: string; columns?: unknown[] },
) {
  return apiFetch<ApiDataTableRead>(
    `/api/v1/projects/${projectId}/workflow-data-tables`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function getDataTable(projectId: string, tableId: string) {
  return apiFetch<ApiDataTableRead>(
    `/api/v1/projects/${projectId}/workflow-data-tables/${tableId}`,
  )
}

export function deleteDataTable(projectId: string, tableId: string) {
  return apiFetch<void>(
    `/api/v1/projects/${projectId}/workflow-data-tables/${tableId}`,
    { method: 'DELETE' },
  )
}

export function insertDataTableRow(
  projectId: string,
  tableId: string,
  data: Record<string, unknown>,
) {
  return apiFetch<ApiDataTableRead>(
    `/api/v1/projects/${projectId}/workflow-data-tables/${tableId}/rows`,
    { method: 'POST', body: JSON.stringify({ data }) },
  )
}

export function exportWorkflow(projectId: string, workflowId: string) {
  return apiFetch<Record<string, unknown>>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/export`,
  )
}

export function listWorkflowRuns(projectId: string, workflowId: string) {
  return apiFetch<ApiWorkflowRun[]>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/runs`,
  )
}

export function getWorkflowRun(projectId: string, workflowId: string, runId: string) {
  return apiFetch<ApiWorkflowRun>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/runs/${runId}`,
  )
}

export interface ExecuteWorkflowBody {
  trigger?: string
  mocks?: Record<string, unknown>
  credentials?: Record<string, Record<string, unknown>>
  pin_data?: Record<string, Record<string, unknown>[]>
  dry_run?: boolean
  background?: boolean
}

export function executeWorkflow(
  projectId: string,
  workflowId: string,
  body: ExecuteWorkflowBody = {},
) {
  return apiFetch<ApiWorkflowRun>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/execute`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export interface ValidateRunResponse {
  ok: boolean
  missing_credentials: {
    credential_type: string
    n8n_name?: string | null
    n8n_id?: string | null
    used_by_nodes?: string[]
  }[]
  unsupported_types: string[]
  triggers: { name: string; type: string }[]
  has_schedule: boolean
  node_count: number
  edge_count: number
  credential_requirements: unknown[]
}

export function validateWorkflowRun(projectId: string, workflowId: string) {
  return apiFetch<ValidateRunResponse>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/validate-run`,
    { method: 'POST', body: '{}' },
  )
}

export function cancelWorkflowRun(projectId: string, workflowId: string, runId: string) {
  return apiFetch<ApiWorkflowRun>(
    `/api/v1/projects/${projectId}/workflows/${workflowId}/runs/${runId}/cancel`,
    { method: 'POST', body: '{}' },
  )
}

export interface ApiWorkflowCredential {
  id: string
  project_id: string
  credential_type: string
  name: string
  created_at: string
  updated_at: string
}

export function listWorkflowCredentials(projectId: string) {
  return apiFetch<ApiWorkflowCredential[]>(
    `/api/v1/projects/${projectId}/workflow-credentials`,
  )
}

export function createWorkflowCredential(
  projectId: string,
  body: { credential_type: string; name: string; payload: Record<string, unknown> },
) {
  return apiFetch<ApiWorkflowCredential>(
    `/api/v1/projects/${projectId}/workflow-credentials`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function deleteWorkflowCredential(projectId: string, credentialId: string) {
  return apiFetch<void>(
    `/api/v1/projects/${projectId}/workflow-credentials/${credentialId}`,
    { method: 'DELETE' },
  )
}
