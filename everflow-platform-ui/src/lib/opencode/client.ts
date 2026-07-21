/**
 * Browser client for OpenCode via Everflow platform proxy.
 * Never talks to sandbox-agent or OpenCode directly.
 */

import { ApiError, getAccessToken, isDemoMode } from '@/lib/api'
import { normalizeMessageList } from './mapParts'
import type {
  OcAgent,
  OcEnsureResult,
  OcEvent,
  OcMessageBundle,
  OcMcpStatus,
  OcProvider,
  OcQuestionRequest,
  OcSession,
} from './types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function base(projectId: string): string {
  return `${API_BASE}/api/v1/projects/${projectId}/opencode`
}

async function ocFetch<T = unknown>(
  projectId: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const url = `${base(projectId)}/${path.replace(/^\//, '')}`
  const res = await fetch(url, { ...init, headers })
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

export function canUseOpenCode(project: {
  fromApi?: boolean
  sandboxStatus?: string
}): boolean {
  if (isDemoMode()) return false
  if (!project.fromApi) return false
  return project.sandboxStatus === 'running'
}

/** Ensure hits dedicated platform route (not the catch-all proxy). */
export async function ensureOpenCode(
  projectId: string,
  forceRestart = false,
): Promise<OcEnsureResult> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/opencode/ensure`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ force_restart: forceRestart }),
  })
  const data = (await res.json().catch(() => ({}))) as { detail?: string }
  if (!res.ok) {
    throw new ApiError(
      res.status,
      typeof data?.detail === 'string' ? data.detail : res.statusText,
      data,
    )
  }
  return data as OcEnsureResult
}

export async function listSessions(projectId: string): Promise<OcSession[]> {
  const data = await ocFetch<OcSession[]>(projectId, 'session')
  return Array.isArray(data) ? data : []
}

export async function createSession(
  projectId: string,
  title?: string,
): Promise<OcSession> {
  return ocFetch(projectId, 'session', {
    method: 'POST',
    body: JSON.stringify(title ? { title } : {}),
  })
}

export async function deleteSession(projectId: string, sessionId: string): Promise<void> {
  await ocFetch(projectId, `session/${sessionId}`, { method: 'DELETE' })
}

export async function updateSession(
  projectId: string,
  sessionId: string,
  body: { title?: string },
): Promise<OcSession> {
  return ocFetch(projectId, `session/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export async function listMessages(
  projectId: string,
  sessionId: string,
): Promise<OcMessageBundle[]> {
  const data = await ocFetch<unknown>(projectId, `session/${sessionId}/message`)
  return normalizeMessageList(data)
}

export async function promptAsync(
  projectId: string,
  sessionId: string,
  body: {
    parts: Array<{ type: string; text?: string }>
    model?: { providerID: string; modelID: string }
    agent?: string
    system?: string
    tools?: Record<string, boolean>
  },
): Promise<void> {
  await ocFetch(projectId, `session/${sessionId}/prompt_async`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function promptSync(
  projectId: string,
  sessionId: string,
  body: {
    parts: Array<{ type: string; text?: string }>
    model?: { providerID: string; modelID: string }
    agent?: string
  },
): Promise<OcMessageBundle> {
  return ocFetch(projectId, `session/${sessionId}/message`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function respondPermission(
  projectId: string,
  sessionId: string,
  permissionId: string,
  response: 'once' | 'always' | 'reject',
  remember?: boolean,
): Promise<void> {
  // Prefer modern permission reply; fall back to session-scoped path
  try {
    await ocFetch(projectId, `permission/${permissionId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ reply: response }),
    })
    return
  } catch {
    await ocFetch(projectId, `session/${sessionId}/permissions/${permissionId}`, {
      method: 'POST',
      body: JSON.stringify({ response, remember }),
    })
  }
}

/** List pending OpenCode question requests (all sessions or filter client-side). */
export async function listQuestions(projectId: string): Promise<OcQuestionRequest[]> {
  try {
    const data = await ocFetch<unknown>(projectId, 'question')
    if (Array.isArray(data)) return data as OcQuestionRequest[]
    if (data && typeof data === 'object') {
      const o = data as { data?: unknown; questions?: unknown; items?: unknown }
      if (Array.isArray(o.data)) return o.data as OcQuestionRequest[]
      if (Array.isArray(o.questions)) return o.questions as OcQuestionRequest[]
      if (Array.isArray(o.items)) return o.items as OcQuestionRequest[]
    }
  } catch {
    /* older OpenCode may lack /question */
  }
  return []
}

/**
 * Reply to a question tool request.
 * answers: one entry per question; each entry is selected label(s).
 *
 * Tries global `/question/{id}/reply` first, then session-scoped path used by
 * newer OpenCode builds.
 */
export async function respondQuestion(
  projectId: string,
  requestId: string,
  answers: string[][],
  sessionId?: string,
): Promise<void> {
  const id = encodeURIComponent(requestId)
  const body = JSON.stringify({ answers })
  try {
    await ocFetch(projectId, `question/${id}/reply`, {
      method: 'POST',
      body,
    })
    return
  } catch (first) {
    if (sessionId) {
      try {
        await ocFetch(
          projectId,
          `session/${encodeURIComponent(sessionId)}/question/${id}/reply`,
          { method: 'POST', body },
        )
        return
      } catch {
        /* fall through */
      }
      // Alternate v2-style path seen in some OpenCode builds
      try {
        await ocFetch(
          projectId,
          `api/session/${encodeURIComponent(sessionId)}/question/${id}/reply`,
          { method: 'POST', body },
        )
        return
      } catch {
        /* fall through */
      }
    }
    throw first
  }
}

export async function rejectQuestion(
  projectId: string,
  requestId: string,
  sessionId?: string,
): Promise<void> {
  const id = encodeURIComponent(requestId)
  try {
    await ocFetch(projectId, `question/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    return
  } catch (first) {
    if (sessionId) {
      try {
        await ocFetch(
          projectId,
          `session/${encodeURIComponent(sessionId)}/question/${id}/reject`,
          { method: 'POST', body: JSON.stringify({}) },
        )
        return
      } catch {
        /* fall through */
      }
    }
    throw first
  }
}

export async function abortSession(projectId: string, sessionId: string): Promise<void> {
  await ocFetch(projectId, `session/${sessionId}/abort`, { method: 'POST' })
}

export async function forkSession(
  projectId: string,
  sessionId: string,
  messageID?: string,
): Promise<OcSession> {
  return ocFetch(projectId, `session/${sessionId}/fork`, {
    method: 'POST',
    body: JSON.stringify(messageID ? { messageID } : {}),
  })
}

export async function revertMessage(
  projectId: string,
  sessionId: string,
  messageID: string,
): Promise<void> {
  await ocFetch(projectId, `session/${sessionId}/revert`, {
    method: 'POST',
    body: JSON.stringify({ messageID }),
  })
}

export async function listProviders(projectId: string): Promise<{
  providers: OcProvider[]
  default?: Record<string, string>
  connected?: string[]
}> {
  // Prefer combined endpoint; fall back to /provider
  try {
    const cfg = await ocFetch<{
      providers: OcProvider[]
      default?: Record<string, string>
    }>(projectId, 'config/providers')
    let connected: string[] = []
    try {
      const prov = await ocFetch<{ connected?: string[] }>(projectId, 'provider')
      connected = prov.connected || []
    } catch {
      /* optional */
    }
    return { ...cfg, connected }
  } catch {
    const prov = await ocFetch<{
      all?: OcProvider[]
      connected?: string[]
      default?: Record<string, string>
    }>(projectId, 'provider')
    return {
      providers: prov.all || [],
      default: prov.default,
      connected: prov.connected,
    }
  }
}

export async function setProviderAuth(
  projectId: string,
  providerId: string,
  key: string,
): Promise<void> {
  await ocFetch(projectId, `auth/${providerId}`, {
    method: 'PUT',
    body: JSON.stringify({ type: 'api', key }),
  })
}

export async function listAgents(projectId: string): Promise<OcAgent[]> {
  const data = await ocFetch<OcAgent[]>(projectId, 'agent')
  return Array.isArray(data) ? data : []
}

export async function listMcp(projectId: string): Promise<Record<string, OcMcpStatus>> {
  const data = await ocFetch<Record<string, OcMcpStatus>>(projectId, 'mcp')
  return data && typeof data === 'object' ? data : {}
}

export async function addMcp(
  projectId: string,
  name: string,
  config: Record<string, unknown>,
): Promise<unknown> {
  return ocFetch(projectId, 'mcp', {
    method: 'POST',
    body: JSON.stringify({ name, config }),
  })
}

export async function patchConfig(
  projectId: string,
  patch: Record<string, unknown>,
): Promise<unknown> {
  return ocFetch(projectId, 'config', {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export async function runCommand(
  projectId: string,
  sessionId: string,
  command: string,
  args = '',
): Promise<OcMessageBundle> {
  return ocFetch(projectId, `session/${sessionId}/command`, {
    method: 'POST',
    body: JSON.stringify({ command, arguments: args }),
  })
}

/** Subscribe to OpenCode SSE events. Returns abort controller. */
export function subscribeEvents(
  projectId: string,
  onEvent: (ev: OcEvent) => void,
  onError?: (err: Error) => void,
): AbortController {
  const controller = new AbortController()
  const token = getAccessToken()
  const url = `${base(projectId)}/event`

  ;(async () => {
    try {
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`SSE failed: ${res.status}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const chunks = buf.split('\n\n')
        buf = chunks.pop() || ''
        for (const chunk of chunks) {
          const lines = chunk.split('\n')
          let dataLine = ''
          for (const line of lines) {
            if (line.startsWith('data:')) {
              dataLine += line.slice(5).trim()
            }
          }
          if (!dataLine) continue
          try {
            const parsed = JSON.parse(dataLine) as OcEvent
            onEvent(parsed)
          } catch {
            /* ignore malformed */
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      onError?.(err as Error)
    }
  })()

  return controller
}
