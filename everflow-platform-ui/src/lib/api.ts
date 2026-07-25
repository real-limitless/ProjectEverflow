/**
 * Thin client for everflow-platform-api.
 * Token is stored in localStorage under everflow_access_token.
 * Browser never calls sandbox-agent — only Everflow API.
 *
 * VITE_API_URL:
 *   - unset → http://localhost:8000 (local Vite/dev)
 *   - "" or "/" → same-origin (prebuilt image; nginx proxies /api/)
 *   - absolute URL → that host
 */

function resolveApiBase(): string {
  const raw = import.meta.env.VITE_API_URL as string | undefined
  if (raw === '' || raw === '/') return ''
  if (typeof raw === 'string' && raw.trim()) return raw.replace(/\/$/, '')
  return 'http://localhost:8000'
}

const API_BASE = resolveApiBase()

function wsApiBase(): string {
  if (API_BASE) return API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  if (typeof window === 'undefined') return 'ws://localhost:8000'
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
}

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

export async function getMe(): Promise<{
  id: string
  email: string
  is_superuser?: boolean
  is_active?: boolean
}> {
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

export type OrgMember = {
  id: string
  user_id: string
  email?: string | null
  role: string
  created_at: string
}

export type OrgInvite = {
  id: string
  organization_id: string
  role: string
  email?: string | null
  expires_at: string
  accepted_at?: string | null
  created_at: string
  invite_url?: string | null
  token?: string | null
}

export type GitCredential = {
  id: string
  owner_type: 'user' | 'org' | 'project'
  owner_id: string
  provider: string
  label?: string | null
  scopes: string
  is_default: boolean
  key_hint: string
  created_at: string
  updated_at: string
  last_used_at?: string | null
}

export type SetupStatus = {
  needs_setup: boolean
  environment: string
  warnings: string[]
  sandbox?: {
    enabled?: boolean
    reachable?: boolean | null
    mock?: boolean | null
    error?: string
  } | null
  oauth: { github: boolean; google: boolean }
}

export type AuthProviders = {
  github: boolean
  google: boolean
  password: boolean
}

export type GitRemoteResult = {
  ok: boolean
  exit_code: number
  stdout: string
  stderr: string
  used_credential: boolean
}

export type AdminUser = {
  id: string
  email: string
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
}

export type AdminOrg = {
  id: string
  name: string
  slug: string
  created_at: string
  member_count: number
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
  template_id?: string | null
  preview_device?: string | null
  repos?: ApiProjectRepo[] | null
  /** Harness ids or {id, enabled?} objects persisted for sandbox bootstrap */
  harnesses?: Array<string | { id: string; label?: string; enabled?: boolean }> | null
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
  reconfigure_mode?: string | null
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

export async function getSetupStatus(): Promise<SetupStatus> {
  return apiFetch('/api/v1/setup/status')
}

export async function bootstrapSetup(payload: {
  email: string
  password: string
  org_name: string
  org_slug: string
}): Promise<{
  user_id: string
  email: string
  org_id: string
  org_slug: string
  access_token: string
}> {
  return apiFetch('/api/v1/setup/bootstrap', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getAuthProviders(): Promise<AuthProviders> {
  return apiFetch('/api/v1/auth/providers')
}

export function oauthAuthorizeUrl(provider: 'github' | 'google'): string {
  return `${API_BASE}/api/v1/auth/${provider}/authorize`
}

export async function listOrgMembers(orgId: string): Promise<OrgMember[]> {
  return apiFetch(`/api/v1/orgs/${orgId}/members`)
}

export async function updateOrgMemberRole(
  orgId: string,
  userId: string,
  role: 'owner' | 'admin' | 'member',
): Promise<OrgMember> {
  return apiFetch(`/api/v1/orgs/${orgId}/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  })
}

export async function removeOrgMember(orgId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/orgs/${orgId}/members/${userId}`, { method: 'DELETE' })
}

export async function createOrgInvite(
  orgId: string,
  payload?: { role?: 'admin' | 'member'; email?: string; expires_hours?: number },
): Promise<OrgInvite> {
  return apiFetch(`/api/v1/orgs/${orgId}/invites`, {
    method: 'POST',
    body: JSON.stringify(payload ?? { role: 'member' }),
  })
}

export async function acceptInvite(token: string): Promise<{
  organization_id: string
  organization_name: string
  organization_slug: string
  role: string
}> {
  return apiFetch(`/api/v1/invites/${encodeURIComponent(token)}/accept`, {
    method: 'POST',
  })
}

export async function listMyGitCredentials(): Promise<GitCredential[]> {
  return apiFetch('/api/v1/me/git-credentials')
}

export async function createMyGitCredential(payload: {
  provider?: string
  token: string
  label?: string
  scopes?: string
  is_default?: boolean
}): Promise<GitCredential> {
  return apiFetch('/api/v1/me/git-credentials', {
    method: 'POST',
    body: JSON.stringify({ provider: 'github', ...payload }),
  })
}

export async function deleteMyGitCredential(credId: string): Promise<void> {
  await apiFetch(`/api/v1/me/git-credentials/${credId}`, { method: 'DELETE' })
}

export async function listOrgGitCredentials(orgId: string): Promise<GitCredential[]> {
  return apiFetch(`/api/v1/orgs/${orgId}/git-credentials`)
}

export async function createOrgGitCredential(
  orgId: string,
  payload: { provider?: string; token: string; label?: string; is_default?: boolean },
): Promise<GitCredential> {
  return apiFetch(`/api/v1/orgs/${orgId}/git-credentials`, {
    method: 'POST',
    body: JSON.stringify({ provider: 'github', ...payload }),
  })
}

export async function deleteOrgGitCredential(orgId: string, credId: string): Promise<void> {
  await apiFetch(`/api/v1/orgs/${orgId}/git-credentials/${credId}`, { method: 'DELETE' })
}

export async function gitPull(
  projectId: string,
  body: { path?: string; remote?: string; branch?: string } = {},
): Promise<GitRemoteResult> {
  return apiFetch(`/api/v1/projects/${projectId}/git/pull`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function gitPush(
  projectId: string,
  body: { path?: string; remote?: string; branch?: string } = {},
): Promise<GitRemoteResult> {
  return apiFetch(`/api/v1/projects/${projectId}/git/push`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  return apiFetch('/api/v1/admin/users')
}

export async function deactivateAdminUser(userId: string): Promise<AdminUser> {
  return apiFetch(`/api/v1/admin/users/${userId}/deactivate`, { method: 'PATCH' })
}

export async function activateAdminUser(userId: string): Promise<AdminUser> {
  return apiFetch(`/api/v1/admin/users/${userId}/activate`, { method: 'PATCH' })
}

export async function listAdminOrgs(): Promise<AdminOrg[]> {
  return apiFetch('/api/v1/admin/orgs')
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
    template_id?: string
    preview_device?: string
    repos?: Array<{
      id: string
      label: string
      url?: string
      branch?: string
      provider?: string
      local_path?: string
      active?: boolean
    }>
    harnesses?: string[]
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

export async function updateProject(
  projectId: string,
  payload: {
    name?: string
    slug?: string
    description?: string | null
    harnesses?: string[]
    /** Default true when harnesses are sent — bootstrap or recreate sandbox */
    reconfigure_sandbox?: boolean
  },
): Promise<ApiProject> {
  return apiFetch(`/api/v1/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}`, { method: 'DELETE' })
}

const sandboxStatusInflight = new Map<string, Promise<SandboxStatus>>()
const sandboxStatusCache = new Map<string, { at: number; value: SandboxStatus }>()
const SANDBOX_STATUS_TTL_MS = 2000

/** Coalesced status fetch — parallel callers share one request; short TTL under tool load. */
export async function getSandboxStatus(projectId: string): Promise<SandboxStatus> {
  const cached = sandboxStatusCache.get(projectId)
  if (cached && Date.now() - cached.at < SANDBOX_STATUS_TTL_MS) {
    return cached.value
  }
  const existing = sandboxStatusInflight.get(projectId)
  if (existing) return existing

  const pending = apiFetch<SandboxStatus>(`/api/v1/projects/${projectId}/sandbox`)
    .then((st) => {
      sandboxStatusCache.set(projectId, { at: Date.now(), value: st })
      return st
    })
    .finally(() => {
      if (sandboxStatusInflight.get(projectId) === pending) {
        sandboxStatusInflight.delete(projectId)
      }
    })
  sandboxStatusInflight.set(projectId, pending)
  return pending
}

/** Force remove (if any) + provision again. Same as recreate. */
export async function retrySandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/retry`, { method: 'POST' })
}

/** Alias for retry — recreate when DB has a project but agent lost the sandbox. */
export async function recreateSandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/recreate`, { method: 'POST' })
}

/** Apply project harnesses to the sandbox (bootstrap in place or recreate). */
export async function reconfigureSandbox(projectId: string): Promise<SandboxStatus> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/reconfigure`, { method: 'POST' })
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

export type DesktopResizeResult = {
  ok: boolean
  width: number
  height: number
  message: string
}

/** Match guest X framebuffer to the Desktop panel CSS size (noVNC). */
export async function resizeSandboxDesktop(
  projectId: string,
  width: number,
  height: number,
): Promise<DesktopResizeResult> {
  return apiFetch(`/api/v1/projects/${projectId}/sandbox/desktop/resize`, {
    method: 'POST',
    body: JSON.stringify({ width, height }),
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
  const base = wsApiBase()
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
  collection_id?: string | null
  name: string
  description?: string | null
  content_md?: string
  origin: string
  status: string
  chunks?: number | null
  mime?: string | null
  size_label?: string | null
  source_url?: string | null
  content_hash?: string | null
  etag?: string | null
  last_fetched_at?: string | null
  repo_path?: string | null
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type ApiKnowledgeRetrieveHit = {
  canvas_id: string
  canvas_name: string
  chunk_id: string
  text: string
  score: number
  source_url?: string | null
  path?: string | null
  collection_id?: string | null
}

export type ApiKnowledgeCollection = {
  id: string
  project_id: string
  name: string
  visibility: string
  owner_user_id?: string | null
  created_at: string
  updated_at: string
}

export type ApiKnowledgeLink = {
  id: string
  project_id: string
  from_type: string
  from_id: string
  to_type: string
  to_id: string
  rel: string
  created_at: string
}

export type ApiKnowledgeVersion = {
  id: string
  canvas_id: string
  content_md: string
  created_by?: string | null
  label?: string | null
  created_at: string
}

export type ApiKnowledgeEvalSet = {
  id: string
  project_id: string
  name: string
  collection_id?: string | null
  last_score?: number | null
  last_run_at?: string | null
  created_at: string
  updated_at: string
  questions: {
    id: string
    question: string
    expected_canvas_ids?: string[] | null
    expected_notes?: string | null
  }[]
}

export type ApiKnowledgeEvalRunResult = {
  eval_set_id: string
  score: number
  total: number
  hits: number
  results: {
    question_id: string
    question: string
    hit: boolean
    expected_canvas_ids: string[]
    retrieved_canvas_ids: string[]
    expected_names?: string[]
    retrieved_names?: string[]
    top_score?: number | null
  }[]
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
    source_url?: string
    collection_id?: string
    repo_path?: string
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
    collection_id: string | null
    source_url: string | null
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

export async function reindexKnowledgeCanvas(
  projectId: string,
  canvasId: string,
): Promise<ApiKnowledgeCanvas> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}/reindex`, {
    method: 'POST',
  })
}

export async function refreshKnowledgeCanvasSource(
  projectId: string,
  canvasId: string,
): Promise<{ canvas: ApiKnowledgeCanvas; changed: boolean }> {
  return apiFetch(
    `/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}/refresh-source`,
    { method: 'POST' },
  )
}

export async function listKnowledgeCanvasVersions(
  projectId: string,
  canvasId: string,
): Promise<ApiKnowledgeVersion[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/canvases/${canvasId}/versions`)
}

export async function retrieveKnowledge(
  projectId: string,
  body: { query: string; top_k?: number; collection_ids?: string[]; agent_id?: string },
): Promise<{ hits: ApiKnowledgeRetrieveHit[] }> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/retrieve`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function promoteResearchToCanvas(
  projectId: string,
  body: {
    title: string
    mode: 'thread' | 'claims'
    source_url?: string
    article_title?: string
    thread: { role: string; text: string }[]
    article_markdown?: string
  },
): Promise<ApiKnowledgeCanvas> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/research/promote`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function indexKnowledgeRepo(
  projectId: string,
  body?: { collection_name?: string; paths?: string[] },
): Promise<{
  created: number
  updated: number
  skipped: number
  canvas_ids: string[]
  matched_paths?: string[]
  matched_count?: number
  message?: string | null
}> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/index-repo`, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
}

export async function listKnowledgeCollections(
  projectId: string,
): Promise<ApiKnowledgeCollection[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/collections`)
}

export async function createKnowledgeCollection(
  projectId: string,
  body: { name: string; visibility?: string },
): Promise<ApiKnowledgeCollection> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/collections`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateKnowledgeCollection(
  projectId: string,
  collectionId: string,
  body: { name?: string; visibility?: string },
): Promise<ApiKnowledgeCollection> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/collections/${collectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteKnowledgeCollection(
  projectId: string,
  collectionId: string,
): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/knowledge/collections/${collectionId}`, {
    method: 'DELETE',
  })
}

export async function upsertCollectionGrant(
  projectId: string,
  collectionId: string,
  body: { agent_id: string; can_retrieve?: boolean; can_write?: boolean },
): Promise<unknown> {
  return apiFetch(
    `/api/v1/projects/${projectId}/knowledge/collections/${collectionId}/grants`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}

export async function listKnowledgeLinks(projectId: string): Promise<ApiKnowledgeLink[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/links`)
}

export async function listKnowledgeEvalSets(projectId: string): Promise<ApiKnowledgeEvalSet[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/eval-sets`)
}

export async function createKnowledgeEvalSet(
  projectId: string,
  body: {
    name: string
    collection_id?: string
    questions: {
      question: string
      expected_canvas_ids?: string[]
      expected_notes?: string
    }[]
  },
): Promise<ApiKnowledgeEvalSet> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/eval-sets`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateKnowledgeEvalSet(
  projectId: string,
  evalSetId: string,
  body: {
    name?: string
    collection_id?: string | null
    questions?: {
      question: string
      expected_canvas_ids?: string[]
      expected_notes?: string
    }[]
  },
): Promise<ApiKnowledgeEvalSet> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/eval-sets/${evalSetId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteKnowledgeEvalSet(
  projectId: string,
  evalSetId: string,
): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/knowledge/eval-sets/${evalSetId}`, {
    method: 'DELETE',
  })
}

export async function runKnowledgeEvalSet(
  projectId: string,
  evalSetId: string,
): Promise<ApiKnowledgeEvalRunResult> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/eval-sets/${evalSetId}/run`, {
    method: 'POST',
  })
}

export type ApiKnowledgeMindMap = {
  id: string
  project_id: string
  name: string
  mermaid: string
  created_by?: string | null
  created_at: string
  updated_at: string
}

export async function listKnowledgeMindMaps(
  projectId: string,
): Promise<ApiKnowledgeMindMap[]> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/mind-maps`)
}

export async function createKnowledgeMindMap(
  projectId: string,
  body: { name: string; mermaid?: string },
): Promise<ApiKnowledgeMindMap> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/mind-maps`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateKnowledgeMindMap(
  projectId: string,
  mindMapId: string,
  body: Partial<{ name: string; mermaid: string }>,
): Promise<ApiKnowledgeMindMap> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/mind-maps/${mindMapId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteKnowledgeMindMap(
  projectId: string,
  mindMapId: string,
): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/knowledge/mind-maps/${mindMapId}`, {
    method: 'DELETE',
  })
}

export type ApiWebSearchHit = {
  id: string
  title: string
  url: string
  snippet: string
  reader_markdown?: string | null
}

export type ApiWebReadResult = {
  url: string
  title: string
  markdown: string
  content_type: string
}

export async function searchKnowledgeWeb(
  projectId: string,
  q: string,
): Promise<ApiWebSearchHit[]> {
  const params = new URLSearchParams({ q })
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/web-search?${params}`)
}

/** Fetch a public page and extract clean Markdown for Reader mode. */
export async function fetchKnowledgeWebRead(
  projectId: string,
  url: string,
): Promise<ApiWebReadResult> {
  return apiFetch(`/api/v1/projects/${projectId}/knowledge/web-read`, {
    method: 'POST',
    body: JSON.stringify({ url }),
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

// ── Studio: test suites + cases ───────────────────────────────────────────────

export type ApiTestCase = {
  id: string
  suite_id: string
  project_id: string
  name: string
  type: string
  command: string
  last_status?: string | null
  last_error?: string | null
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type ApiTestSuite = {
  id: string
  project_id: string
  name: string
  description?: string | null
  cases: ApiTestCase[]
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type ApiTestSuiteRunResult = {
  suite_id: string
  status: 'passed' | 'failed'
  summary: string
  passed: number
  failed: number
  results: Array<{
    case_id: string
    name: string
    status: 'passed' | 'failed' | 'skipped'
    exit_code?: number | null
    stdout?: string
    stderr?: string
    error?: string | null
  }>
}

export async function listTestSuites(projectId: string): Promise<ApiTestSuite[]> {
  return apiFetch(`/api/v1/projects/${projectId}/tests/suites`)
}

export async function createTestSuite(
  projectId: string,
  body: { name: string; description?: string },
): Promise<ApiTestSuite> {
  return apiFetch(`/api/v1/projects/${projectId}/tests/suites`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function createTestCase(
  projectId: string,
  suiteId: string,
  body: { name: string; type?: string; command?: string },
): Promise<ApiTestCase> {
  return apiFetch(`/api/v1/projects/${projectId}/tests/suites/${suiteId}/cases`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateTestCase(
  projectId: string,
  suiteId: string,
  caseId: string,
  body: Partial<{ name: string; type: string; command: string }>,
): Promise<ApiTestCase> {
  return apiFetch(`/api/v1/projects/${projectId}/tests/suites/${suiteId}/cases/${caseId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteTestCase(
  projectId: string,
  suiteId: string,
  caseId: string,
): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/tests/suites/${suiteId}/cases/${caseId}`, {
    method: 'DELETE',
  })
}

export async function runTestSuite(
  projectId: string,
  suiteId: string,
): Promise<ApiTestSuiteRunResult> {
  return apiFetch(`/api/v1/projects/${projectId}/tests/suites/${suiteId}/run`, {
    method: 'POST',
  })
}

// ── Studio: HTTP tools (Tools panel) ─────────────────────────────────────────

export type ApiHttpTool = {
  id: string
  project_id: string
  name: string
  method: string
  url_template: string
  enabled: boolean
  created_by?: string | null
  created_at: string
  updated_at: string
}

export type ApiHttpToolExecuteResult = {
  ok: boolean
  status_code: number | null
  url: string
  method: string
  headers: Record<string, string>
  body: string
  truncated: boolean
  error: string | null
  elapsed_ms: number
}

export async function listHttpTools(projectId: string): Promise<ApiHttpTool[]> {
  return apiFetch(`/api/v1/projects/${projectId}/http-tools`)
}

export async function createHttpTool(
  projectId: string,
  body: {
    name: string
    method?: string
    url_template: string
    enabled?: boolean
  },
): Promise<ApiHttpTool> {
  return apiFetch(`/api/v1/projects/${projectId}/http-tools`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function updateHttpTool(
  projectId: string,
  toolId: string,
  body: Partial<{
    name: string
    method: string
    url_template: string
    enabled: boolean
  }>,
): Promise<ApiHttpTool> {
  return apiFetch(`/api/v1/projects/${projectId}/http-tools/${toolId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function deleteHttpTool(projectId: string, toolId: string): Promise<void> {
  await apiFetch(`/api/v1/projects/${projectId}/http-tools/${toolId}`, { method: 'DELETE' })
}

export async function testHttpTool(
  projectId: string,
  toolId: string,
  body: {
    path_params?: Record<string, string>
    query?: Record<string, string>
    headers?: Record<string, string>
    body?: unknown
  } = {},
): Promise<ApiHttpToolExecuteResult> {
  return apiFetch(`/api/v1/projects/${projectId}/http-tools/${toolId}/test`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function executeHttpTool(
  projectId: string,
  toolId: string,
  body: {
    path_params?: Record<string, string>
    query?: Record<string, string>
    headers?: Record<string, string>
    body?: unknown
  } = {},
): Promise<ApiHttpToolExecuteResult> {
  return apiFetch(`/api/v1/projects/${projectId}/http-tools/${toolId}/execute`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export type MarketplaceKindApi = 'skill' | 'command' | 'plugin' | 'tool' | 'mcp'

export async function getMarketplaceCatalog(): Promise<import('@/data/marketplace').MarketplaceCatalog> {
  return apiFetch('/api/v1/marketplace/catalog')
}

export async function getMarketplaceItem(
  kind: MarketplaceKindApi,
  itemId: string,
): Promise<import('@/data/marketplace').MarketplaceItem> {
  return apiFetch(
    `/api/v1/marketplace/items/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}`,
  )
}

export async function getMarketplaceItemContent(
  kind: MarketplaceKindApi,
  itemId: string,
): Promise<import('@/data/marketplace/types').MarketplaceItemContent> {
  return apiFetch(
    `/api/v1/marketplace/items/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/content`,
  )
}

export async function getMarketplaceInstalled(
  projectId: string,
): Promise<import('@/data/marketplace').MarketplaceInstalledResponse> {
  return apiFetch(`/api/v1/projects/${projectId}/marketplace/installed`)
}

export async function installMarketplaceItem(
  projectId: string,
  kind: MarketplaceKindApi,
  itemId: string,
): Promise<{ ok: boolean; kind: string; item_id: string; harness?: unknown; http_tool?: unknown }> {
  return apiFetch(`/api/v1/projects/${projectId}/marketplace/install`, {
    method: 'POST',
    body: JSON.stringify({ kind, item_id: itemId }),
  })
}

export async function uninstallMarketplaceItem(
  projectId: string,
  kind: MarketplaceKindApi,
  itemId: string,
): Promise<{ ok: boolean; kind: string; item_id: string }> {
  return apiFetch(`/api/v1/projects/${projectId}/marketplace/uninstall`, {
    method: 'POST',
    body: JSON.stringify({ kind, item_id: itemId }),
  })
}

export type AiUsageEventPayload = {
  session_id: string
  message_id: string
  provider?: string | null
  model?: string | null
  input_tokens?: number
  output_tokens?: number
  reasoning_tokens?: number
  cache_read_tokens?: number
  cache_write_tokens?: number
  total_tokens?: number | null
  duration_ms?: number | null
  ttft_ms?: number | null
  occurred_at?: string | null
  completed?: boolean
}

export type AiUsageEventRead = {
  id: string
  organization_id: string
  project_id: string
  user_id: string
  session_id: string
  message_id: string
  provider: string | null
  model: string | null
  input_tokens: number
  output_tokens: number
  reasoning_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  total_tokens: number
  duration_ms: number | null
  ttft_ms: number | null
  occurred_at: string
  created_at: string
}

export type AiUsageSummary = {
  scope: 'me' | 'org'
  from: string
  to: string
  totals: {
    messages: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    projects: number
    users: number
    sessions: number
  }
  series_daily: Array<{ date: string; tokens: number; messages: number }>
  by_model: Array<{
    provider: string | null
    model: string | null
    tokens: number
    messages: number
  }>
  by_project: Array<{
    project_id: string
    project_name: string
    tokens: number
    messages: number
  }>
  by_user: Array<{
    user_id: string
    email: string
    tokens: number
    messages: number
  }>
}

export async function reportUsageEvent(
  projectId: string,
  payload: AiUsageEventPayload,
): Promise<AiUsageEventRead> {
  return apiFetch(`/api/v1/projects/${projectId}/usage/events`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function reportUsageEventsBatch(
  projectId: string,
  events: AiUsageEventPayload[],
): Promise<{ accepted: number; skipped: number; events: AiUsageEventRead[] }> {
  return apiFetch(`/api/v1/projects/${projectId}/usage/events/batch`, {
    method: 'POST',
    body: JSON.stringify({ events }),
  })
}

export async function getUsageSummary(
  orgId: string,
  params: {
    scope?: 'me' | 'org'
    from?: string
    to?: string
    project_id?: string
  } = {},
): Promise<AiUsageSummary> {
  const q = new URLSearchParams()
  if (params.scope) q.set('scope', params.scope)
  if (params.from) q.set('from', params.from)
  if (params.to) q.set('to', params.to)
  if (params.project_id) q.set('project_id', params.project_id)
  const qs = q.toString()
  return apiFetch(`/api/v1/orgs/${orgId}/usage/summary${qs ? `?${qs}` : ''}`)
}

export { API_BASE }
