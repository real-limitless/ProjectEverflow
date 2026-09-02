export type SeatKind = 'human' | 'bot'
export type SurfaceMode = 'room' | 'harness' | 'chart'

export interface Team {
  id: string
  project_id: string
  name: string
  slug: string
  mention: string
  lane: string
  description: string
  conductor_seat_id: string | null
}

export interface Seat {
  id: string
  project_id: string
  team_id: string | null
  kind: SeatKind | string
  slug: string
  name: string
  role: string
  lane: string
  description: string
  reports_to_id: string | null
  owner_user_id: string | null
  agent_slug: string | null
  is_conductor: boolean
  paused: boolean
  fired: boolean
  opencode_session_id: string | null
  worktree_path: string | null
  budget_tokens: number
  permission: Record<string, string>
  tools: string[]
  status: string
}

export interface ChartEdge {
  from_id: string
  to_id: string
}

export interface ChartSnapshot {
  teams: Team[]
  seats: Seat[]
  edges: ChartEdge[]
  constitution_md: string
}

export interface Channel {
  id: string
  project_id: string
  team_id: string | null
  slug: string
  name: string
  kind: string
}

export interface ChannelMessage {
  id: string
  channel_id: string
  thread_id: string | null
  author_user_id: string | null
  author_seat_id: string | null
  body: string
  kind: string
  mentions: Array<{ kind?: string; slug?: string; id?: string }>
  run_id: string | null
  created_at: string
}

export interface RunNode {
  id: string
  run_id: string
  seat_id: string | null
  key: string
  label: string
  status: string
  brief: string
  result: string
  sort_order: number
  depends_on: string[]
}

export interface OrgRun {
  id: string
  project_id: string
  channel_id: string | null
  thread_id: string | null
  title: string
  sentence: string
  status: string
  compiled_graph: Record<string, unknown>
  nodes: RunNode[]
  created_at: string
}

export interface BusEvent {
  id: string
  verb: string
  status: string
  from_seat_id: string | null
  to_seat_id: string | null
  payload: Record<string, unknown>
  error: string | null
  created_at: string
}
