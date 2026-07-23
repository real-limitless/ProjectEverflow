/**
 * Project deploy API — SSH keys, nodes, routes, compose discovery.
 */

import { apiFetch } from '@/lib/api'

export interface ApiDeploySshKey {
  id: string
  project_id: string
  fingerprint: string
  public_key: string
  created_by?: string | null
  created_at: string
  updated_at?: string
}

export interface ApiDeployNode {
  id: string
  project_id: string
  name: string
  host: string
  port: number
  ssh_user: string
  tags: string[]
  status: string
  created_by?: string | null
  created_at: string
  updated_at: string
}

export interface ApiDeployRoute {
  id: string
  node_id: string
  host_header: string
  service_name: string
  service_port: number
  path_prefix: string
  created_at: string
  updated_at: string
}

export interface ApiComposeFiles {
  files: string[]
  message?: string | null
}

export interface ApiDeployRunStub {
  id: string
  project_id: string
  node_id: string | null
  compose_file: string | null
  action: string
  status: string
  message?: string | null
  created_at: string
}

export function listDeployKeys(projectId: string) {
  return apiFetch<ApiDeploySshKey[]>(`/api/v1/projects/${projectId}/deploy/keys`)
}

export function generateDeployKey(projectId: string) {
  return apiFetch<ApiDeploySshKey>(`/api/v1/projects/${projectId}/deploy/keys/generate`, {
    method: 'POST',
  })
}

export function listDeployNodes(projectId: string) {
  return apiFetch<ApiDeployNode[]>(`/api/v1/projects/${projectId}/deploy/nodes`)
}

export function createDeployNode(
  projectId: string,
  body: {
    name: string
    host: string
    port?: number
    ssh_user?: string
    tags?: string[]
    status?: string
  },
) {
  return apiFetch<ApiDeployNode>(`/api/v1/projects/${projectId}/deploy/nodes`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function deleteDeployNode(projectId: string, nodeId: string) {
  return apiFetch<void>(`/api/v1/projects/${projectId}/deploy/nodes/${nodeId}`, {
    method: 'DELETE',
  })
}

export function listComposeFiles(projectId: string) {
  return apiFetch<ApiComposeFiles>(`/api/v1/projects/${projectId}/deploy/compose-files`)
}

export function listDeployRoutes(projectId: string, nodeId: string) {
  return apiFetch<ApiDeployRoute[]>(
    `/api/v1/projects/${projectId}/deploy/nodes/${nodeId}/routes`,
  )
}

export function createDeployRoute(
  projectId: string,
  nodeId: string,
  body: {
    host_header: string
    service_name: string
    service_port?: number
    path_prefix?: string
  },
) {
  return apiFetch<ApiDeployRoute>(
    `/api/v1/projects/${projectId}/deploy/nodes/${nodeId}/routes`,
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}

export function deleteDeployRoute(projectId: string, nodeId: string, routeId: string) {
  return apiFetch<void>(
    `/api/v1/projects/${projectId}/deploy/nodes/${nodeId}/routes/${routeId}`,
    { method: 'DELETE' },
  )
}

export function createDeployRunStub(
  projectId: string,
  body: { node_id: string; compose_file: string; action?: string },
) {
  return apiFetch<ApiDeployRunStub>(`/api/v1/projects/${projectId}/deploy/stub`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export interface ApiDeployRunResult {
  ok: boolean
  project_id: string
  remote_dir: string
  compose_path: string
  routes_path: string
  log_lines: string[]
  error?: string | null
}

/** Live SSH compose-up using stored deploy key + node routes. */
export function createDeployRun(
  projectId: string,
  body: { node_id: string; compose_file: string; dry_run?: boolean },
) {
  return apiFetch<ApiDeployRunResult>(`/api/v1/projects/${projectId}/deploy/runs`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
