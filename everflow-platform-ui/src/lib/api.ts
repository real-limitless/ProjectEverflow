/**
 * Thin client for everflow-platform-api.
 * Token is stored in localStorage under everflow_access_token.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const TOKEN_KEY = 'everflow_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
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

export type Project = {
  id: string
  organization_id: string
  name: string
  slug: string
  description: string | null
  created_at: string
  updated_at: string
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

export async function listProjects(orgId: string): Promise<Project[]> {
  return apiFetch(`/api/v1/orgs/${orgId}/projects`)
}

export async function createProject(
  orgId: string,
  payload: { name: string; slug: string; description?: string },
): Promise<Project> {
  return apiFetch(`/api/v1/orgs/${orgId}/projects`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export { API_BASE }
