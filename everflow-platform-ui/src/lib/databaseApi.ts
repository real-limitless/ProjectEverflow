/**
 * Project database API (sandbox Postgres via psql).
 */

import { apiFetch } from '@/lib/api'

export interface ApiDatabaseStatus {
  status: 'ready' | 'not_provisioned' | 'unreachable' | 'no_sandbox' | 'error' | string
  engine?: string | null
  display_url?: string | null
  psql_available: boolean
  message?: string | null
  harness_installed: boolean
}

export interface ApiDatabaseTable {
  name: string
  schema_name: string
  rows?: number | null
  size?: string | null
}

export interface ApiDatabaseTables {
  tables: ApiDatabaseTable[]
  status: string
  message?: string | null
}

export interface ApiDatabaseQueryResult {
  columns: string[]
  rows: string[][]
  row_count: number
  truncated: boolean
  error?: string | null
}

export function getDatabaseStatus(projectId: string) {
  return apiFetch<ApiDatabaseStatus>(`/api/v1/projects/${projectId}/database/status`)
}

export function listDatabaseTables(projectId: string) {
  return apiFetch<ApiDatabaseTables>(`/api/v1/projects/${projectId}/database/tables`)
}

export function runDatabaseQuery(
  projectId: string,
  body: { sql: string; limit?: number },
) {
  return apiFetch<ApiDatabaseQueryResult>(`/api/v1/projects/${projectId}/database/query`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
