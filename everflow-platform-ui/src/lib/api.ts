/**
 * Thin client for everflow-platform-api.
 * Token is stored in localStorage under everflow_access_token.
 * Browser never calls sandbox-agent — only Everflow API.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const TOKEN_KEY = 'everflow_access_token'
const ORG_KEY = 'everflow_org_id'

export function isDemoMode(): boolean {
  return import.meta.env.VITE_DEMO_MODE === 'true'
}

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getStoredOrgId(): string | null {
  return localStorage.getItem(ORG_KEY)
}

export function setStoredOrgId(id: string | null): void {
  if (id) localStorage.setItem(ORG_KEY, id)
  else localStorage.removeItem(ORG_KEY)
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

type UnauthorizedHandler = () => void
let onUnauthorized: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (res.status === 204) return undefined as T

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) {
      onUnauthorized()
    }
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : res.statusText
    throw new ApiError(res.status, detail, data)
  }
  return data as T
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch(`${API_BASE}/api/v1/auth/jwt/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  const data = (await res.json()) as { access_token?: string; detail?: string }
  if (!res.ok || !data.access_token) {
    throw new ApiError(res.status, data.detail ?? 'Login failed', data)
  }
  setAccessToken(data.access_token)
  return data.access_token
}

export async function register(email: string, password: string): Promise<void> {
  await apiFetch('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function logout(): void {
  setAccessToken(null)
  setStoredOrgId(null)
}

export async function getMe(): Promise<{ id: string; email: string }> {
  return apiFetch('/api/v1/users/me')
}

export type Org = {
  id: string
  name: string
  slug: string
  role?: string
  created_at: string
  updated_at: string
}

export type ApiProjectRepo = {
  id: string
  label: string
  url?: string | null
  branch?: string | null
  provider?: string | null
  local_path?: string | null
  active?: boolean | null
  clone_status?: string | null
  clone_error?: string | null
}

export type ApiProject = {
  id: string
  organization_id: string
  name: string
  slug: string
  description: string | null
  repos?: ApiProjectRepo[] | null
  sandbox_name?: string | null
  sandbox_status?: string
  sandbox_image?: string | null
  sandbox_error?: string | null
  sandbox_created_at?: string | null
  created_at: string
  updated_at: string
}

export type SandboxStatus = {
  project_id: string
  sandbox_name: string | null
  status: string
  image?: string | null
  error?: string | null
  created_at?: string | null
  agent?: Record<string, unknown> | null
}

export type SandboxExecResult = {
  exit_code: number
  stdout: string
  stderr: string
}

export type SandboxFsEntry = {
  path: string
  name: string
  is_dir: boolean
  size: number | null
}

export async function listOrgs(): Promise<Org[]> {
  return apiFetch('/api/v1/orgs')
}

export async function createOrg(name: string, slug: string): Promise<Org> {
  return apiFetch('/api/v1/orgs', {
    method: 'POST',
    body: JSON.stringify({ name, slug }),
  })
}

export async function listProjects(orgId: string): Promise<ApiProject[]> {
  return apiFetch(`/api/v1/orgs/${orgId}/projects`)
}

export async function createProject(
  orgId: string,
  payload: {
    name: string
    slug: string
    description?: string
    repos?: Array<{
      id: string
      label: string
      url?: string
      branch?: string
      provider?: string
      local_path?: string
      active?: boolean
    }>
  },
): Promise<ApiProject> {
  return apiFetch(`/api/v1/orgs/${orgId}/projects`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getProject(projectId: string): Promise<ApiProject> {
  return apiFetch(`/api/v1/projects/${projectId}`)
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}`, { method: 'DELETE' })
}

export async function getSandboxStatus(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox`)
}

/** Force remove (if any) + provision again. Same as recreate. */
export async function retrySandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/retry`, { method: 'POST' })
}

/** Alias for retry — recreate when DB has a project but agent lost the sandbox. */
export async function recreateSandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/recreate`, { method: 'POST' })
}

export async function startSandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/start`, { method: 'POST' })
}

export async function stopSandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/stop`, { method: 'POST' })
}

export async function execInSandbox(
  projectId: string,
  payload: {
    cmd: string
    args?: string[]
    cwd?: string
    env?: Record<string, string>
    timeout_seconds?: number
  },
): Promise<SandboxExecResult> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/exec`, {
    method: 'POST',
    body: JSON.stringify({
      cmd: payload.cmd,
      args: payload.args ?? [],
      cwd: payload.cwd ?? null,
      env: payload.env ?? {},
      timeout_seconds: payload.timeout_seconds ?? 120,
    }),
  })
}

/** Run a free-form shell line via `sh -c` inside the project sandbox. */
export async function execShellLine(
  projectId: string,
  line: string,
  opts?: { cwd?: string; timeout_seconds?: number },
): Promise<SandboxExecResult> {
  return execInSandbox(projectId, {
    cmd: 'sh',
    args: ['-c', line],
    cwd: opts?.cwd,
    timeout_seconds: opts?.timeout_seconds,
  })
}

export async function listSandboxFs(
  projectId: string,
  path = '.',
): Promise<SandboxFsEntry[]> {
  const q = new URLSearchParams({ path })
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/fs?${q}`)
}

export async function readSandboxFs(projectId: string, path: string): Promise<string> {
  const q = new URLSearchParams({ path })
  const token = getAccessToken()
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/sandbox/fs/content?${q}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) onUnauthorized()
    const text = await res.text()
    throw new ApiError(res.status, text || res.statusText)
  }
  return res.text()
}

export async function writeSandboxFs(
  projectId: string,
  path: string,
  content: string,
): Promise<void> {
  const q = new URLSearchParams({ path })
  await apiFetch(`/api/v1/projects/${projectId}/sandbox/fs/content?${q}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

/** AI provider vault (encrypted on server; never returns raw keys). */
export type ProviderName = 'openrouter' | 'openai' | 'anthropic' | 'xai' | 'custom'

export type ProviderCatalogItem = {
  id: string
  name: string
  description: string
  scopes: string[]
}

export type ProviderCredential = {
  id: string
  owner_type: 'user' | 'project'
  owner_id: string
  provider: string
  label: string | null
  scopes: string[]
  is_default: boolean
  key_hint: string | null
  created_at: string
  updated_at: string
  last_used_at: string | null
}

export async function listProviderCatalog(): Promise<ProviderCatalogItem[]> {
  return apiFetch('/api/v1/providers/catalog')
}

export async function listMyProviders(): Promise<ProviderCredential[]> {
  return apiFetch('/api/v1/me/providers')
}

export async function createMyProvider(payload: {
  provider: ProviderName
  api_key: string
  label?: string
  scopes?: string[]
  is_default?: boolean
}): Promise<ProviderCredential> {
  return apiFetch('/api/v1/me/providers', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteMyProvider(credId: string): Promise<void> {
  await apiFetch(`/api/v1/me/providers/${credId}`, { method: 'DELETE' })
}

export async function listProjectProviders(
  projectId: string,
): Promise<ProviderCredential[]> {
  return apiFetch(`/api/v1/projects/${projectId}/providers`)
}

export async function createProjectProvider(
  projectId: string,
  payload: {
    provider: ProviderName
    api_key: string
    label?: string
    scopes?: string[]
    is_default?: boolean
  },
): Promise<ProviderCredential> {
  return apiFetch(`/api/v1/projects/${projectId}/providers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteProjectProvider(
  projectId: string,
  credId: string,
): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/providers/${credId}`, {
    method: 'DELETE',
  })
}

export type ProviderInjectResult = {
  injected: boolean
  reason?: string
  env_keys: string[]
  opencode_providers: string[]
  path?: string | null
  error?: string
}

/** Resolve vault keys for the project and inject into the running sandbox. */
export async function injectProjectProviders(
  projectId: string,
): Promise<ProviderInjectResult> {
  return apiFetch(`/api/v1/projects/${projectId}/providers/inject`, {
    method: 'POST',
  })
}

export function slugifyOrg(email: string): string {
  const local = email.split('@')[0] || 'user'
  const base = local
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
  return base || 'workspace'
}

/**
 * Ensure the user has at least one org; return preferred org id.
 */
export async function ensureOrg(email: string): Promise<Org> {
  const orgs = await listOrgs()
  const stored = getStoredOrgId()
  if (stored) {
    const match = orgs.find((o) => o.id === stored)
    if (match) return match
  }
  if (orgs.length > 0) {
    setStoredOrgId(orgs[0].id)
    return orgs[0]
  }
  const slugBase = slugifyOrg(email)
  let slug = slugBase
  let attempt = 0
  // Retry slug collisions
  while (attempt < 5) {
    try {
      const org = await createOrg(`${email.split('@')[0] || 'User'}'s workspace`, slug)
      setStoredOrgId(org.id)
      return org
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        attempt += 1
        slug = `${slugBase}-${Math.random().toString(36).slice(2, 6)}`
        continue
      }
      throw e
    }
  }
  throw new ApiError(409, 'Could not create organization')
}

/**
 * WebSocket URL for interactive sandbox PTY shell.
 * Browser connects here only (JWT in query) — never to sandbox-agent.
 */
export function sandboxShellWsUrl(
  projectId: string,
  opts?: { cmd?: string; cwd?: string },
): string {
  const token = getAccessToken() || ''
  const base = API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  const q = new URLSearchParams({ token })
  if (opts?.cmd) q.set('cmd', opts.cmd)
  if (opts?.cwd) q.set('cwd', opts.cwd)
  return `${base}/api/v1/projects/${projectId}/sandbox/shell?${q}`
}

export type SandboxListeningPort = {
  port: number
  address: string
  protocol: string
  process: string | null
  http_likely: boolean
  label: string
}

export type SandboxPortsResponse = {
  sandbox_name: string
  ports: SandboxListeningPort[]
}

export type PreviewEndpoint = {
  endpoint_id: string
  port: number
  sandbox_name: string
  url: string
  ticket: string
  expires_at: number
}

/** Listening ports inside the project sandbox (for Preview dropdown). */
export async function listSandboxPorts(
  projectId: string,
  opts?: { probe?: boolean },
): Promise<SandboxPortsResponse> {
  const q = new URLSearchParams()
  if (opts?.probe) q.set('probe', 'true')
  const suffix = q.toString() ? `?${q}` : ''
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/ports${suffix}`)
}

/**
 * Create or reuse a GUID preview host for a sandbox port.
 * Returns absolute URL + short-lived ticket for the iframe.
 */
export async function createPreviewEndpoint(
  projectId: string,
  port: number,
): Promise<PreviewEndpoint> {
  return apiFetch(`/api/v1/projects/${projectId}/preview/endpoints`, {
    method: 'POST',
    body: JSON.stringify({ port }),
  })
}

/** Build iframe src with ticket on the preview subdomain. */
export function previewIframeSrc(endpoint: PreviewEndpoint, path = '/'): string {
  try {
    const u = new URL(endpoint.url)
    const cleaned = path.startsWith('/') ? path : `/${path}`
    u.pathname = cleaned === '/' ? '/' : cleaned
    u.searchParams.set('ticket', endpoint.ticket)
    return u.href
  } catch {
    const base = endpoint.url.replace(/\/?$/, '/')
    const p = path.startsWith('/') ? path.slice(1) : path
    return `${base}${p}?ticket=${encodeURIComponent(endpoint.ticket)}`
  }
}

// ── Studio: knowledge canvases + project agents (platform API / Everflow MCP) ─

export type ApiKnowledgeCanvas = {
  id: string
  project_id: string
  name: string
  description?: string | null
  content_md?: string
  origin: string
  status: string
  chunks?: number | null
  mime?: string | null
  size_label?: string | null
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type ApiProjectAgent = {
  id: string
  project_id: string
  name: string
  role: string
  description: string
  system_prompt: string
  tools: string[]
  active: boolean
  created_by?: string | null
  created_at: string
  updated_at: string
}

export async function listKnowledgeCanvases(projectId: string): Promise<ApiKnowledgeCanvas[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases`)
}

export async function getKnowledgeCanvas(
  projectId: string,
  canvasId: string,
): Promise<ApiKnowledgeCanvas> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}`)
}

export async function createKnowledgeCanvas(
  projectId: string,
  body: {
    name: string
    description?: string
    content_md?: string
    origin?: string
  },
): Promise<ApiKnowledgeCanvas> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateKnowledgeCanvas(
  projectId: string,
  canvasId: string,
  body: Partial<{
    name: string
    description: string | null
    content_md: string
    status: string
  }>,
): Promise<ApiKnowledgeCanvas> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteKnowledgeCanvas(projectId: string, canvasId: string): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}`, {
    method: 'DELETE',
  })
}

export async function listProjectAgents(projectId: string): Promise<ApiProjectAgent[]> {
  return apiFetch(`/api/v1/projects/${projectId}/agents`)
}

export async function createProjectAgent(
  projectId: string,
  body: {
    name: string
    role?: string
    description?: string
    system_prompt?: string
    tools?: string[]
    active?: boolean
  },
): Promise<ApiProjectAgent> {
  return apiFetch(`/api/v1/projects/${projectId}/agents`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateProjectAgent(
  projectId: string,
  agentId: string,
  body: Partial<{
    name: string
    role: string
    description: string
    system_prompt: string
    tools: string[]
    active: boolean
  }>,
): Promise<ApiProjectAgent> {
  return apiFetch(`/api/v1/projects/${projectId}/agents/${agentId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteProjectAgent(projectId: string, agentId: string): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/agents/${agentId}`, { method: 'DELETE' })
}

export { API_BASE }
