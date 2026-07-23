/**
 * Project background jobs API (detached sandbox commands).
 */

import { apiFetch } from '@/lib/api'

export interface ApiJob {
  id: string
  title: string
  command: string
  cwd?: string | null
  pid?: number | null
  status: string
  log_path?: string | null
  created_at?: string | null
  updated_at?: string | null
  exit_code?: number | null
}

export interface ApiJobLogs {
  job_id: string
  status?: string | null
  tail: number
  content: string
}

export function listJobs(projectId: string) {
  return apiFetch<ApiJob[]>(`/api/v1/projects/${projectId}/jobs`)
}

export function createJob(
  projectId: string,
  body: { title: string; command: string; cwd?: string },
) {
  return apiFetch<ApiJob>(`/api/v1/projects/${projectId}/jobs`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getJobLogs(projectId: string, jobId: string, tail = 200) {
  const q = new URLSearchParams({ tail: String(tail) })
  return apiFetch<ApiJobLogs>(`/api/v1/projects/${projectId}/jobs/${jobId}/logs?${q}`)
}

export function killJob(projectId: string, jobId: string) {
  return apiFetch<ApiJob>(`/api/v1/projects/${projectId}/jobs/${jobId}/kill`, {
    method: 'POST',
  })
}
