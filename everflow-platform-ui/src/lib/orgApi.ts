import { apiFetch, getAccessToken } from '@/lib/api'
import type {
  BusEvent,
  Channel,
  ChannelMessage,
  ChartSnapshot,
  OrgRun,
  Seat,
  Team,
} from '@/types/org'

export async function ensureOrg(projectId: string): Promise<ChartSnapshot> {
  return apiFetch(`/api/v1/projects/${projectId}/org/ensure`, { method: 'POST' })
}

export async function getChart(projectId: string): Promise<ChartSnapshot> {
  return apiFetch(`/api/v1/projects/${projectId}/chart`)
}

export async function getConstitution(projectId: string): Promise<{ constitution_md: string }> {
  return apiFetch(`/api/v1/projects/${projectId}/constitution`)
}

export async function listSeats(projectId: string): Promise<Seat[]> {
  return apiFetch(`/api/v1/projects/${projectId}/seats`)
}

export async function listTeams(projectId: string): Promise<Team[]> {
  return apiFetch(`/api/v1/projects/${projectId}/teams`)
}

export async function attachSeat(projectId: string, seatId: string): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats/${seatId}/attach`, { method: 'POST' })
}

export async function pauseSeat(projectId: string, seatId: string): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats/${seatId}/pause`, { method: 'POST' })
}

export async function resumeSeat(projectId: string, seatId: string): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats/${seatId}/resume`, { method: 'POST' })
}

export async function fireSeat(projectId: string, seatId: string): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats/${seatId}/fire`, { method: 'POST' })
}

export async function reparentSeat(
  projectId: string,
  seatId: string,
  reportsToId: string | null,
): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats/${seatId}/reparent`, {
    method: 'POST',
    body: JSON.stringify({ reports_to_id: reportsToId }),
  })
}

export async function hireSeat(
  projectId: string,
  body: {
    name: string
    slug: string
    template?: string
    kind?: string
    role?: string
    team_id?: string | null
    reports_to_id?: string | null
  },
): Promise<Seat> {
  return apiFetch(`/api/v1/projects/${projectId}/seats`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function listChannels(projectId: string): Promise<Channel[]> {
  return apiFetch(`/api/v1/projects/${projectId}/channels`)
}

export async function listMessages(
  projectId: string,
  channelId: string,
  threadId?: string,
): Promise<ChannelMessage[]> {
  const q = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''
  return apiFetch(`/api/v1/projects/${projectId}/channels/${channelId}/messages${q}`)
}

export async function postMessage(
  projectId: string,
  channelId: string,
  body: string,
  opts?: { threadId?: string; compileRun?: boolean },
): Promise<ChannelMessage> {
  return apiFetch(`/api/v1/projects/${projectId}/channels/${channelId}/messages`, {
    method: 'POST',
    body: JSON.stringify({
      body,
      thread_id: opts?.threadId ?? null,
      compile_run: opts?.compileRun ?? false,
    }),
  })
}

export async function getRun(projectId: string, runId: string): Promise<OrgRun> {
  return apiFetch(`/api/v1/projects/${projectId}/runs/${runId}`)
}

export async function listRuns(projectId: string): Promise<OrgRun[]> {
  return apiFetch(`/api/v1/projects/${projectId}/runs`)
}

export async function compileRun(projectId: string, sentence: string): Promise<OrgRun> {
  return apiFetch(`/api/v1/projects/${projectId}/runs/compile`, {
    method: 'POST',
    body: JSON.stringify({ sentence }),
  })
}

export async function dispatchBus(
  projectId: string,
  body: {
    verb: string
    from_seat_id?: string
    to_seat_id?: string
    run_id?: string
    payload?: Record<string, unknown>
  },
): Promise<BusEvent> {
  return apiFetch(`/api/v1/projects/${projectId}/bus`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function exportOrgYaml(projectId: string): Promise<string> {
  const token = getAccessToken()
  const raw = import.meta.env.VITE_API_URL as string | undefined
  const base =
    raw === '' || raw === '/'
      ? ''
      : typeof raw === 'string' && raw.trim()
        ? raw.replace(/\/$/, '')
        : 'http://localhost:8000'
  const res = await fetch(`${base}/api/v1/projects/${projectId}/org/export.yaml`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  return res.text()
}
