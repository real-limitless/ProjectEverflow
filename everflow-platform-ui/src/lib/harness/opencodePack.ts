/**
 * Project OpenCode harness pack client (agents, skills, MCP → sandbox workspace).
 */
import { apiFetch } from '@/lib/api'
import type { AgentDefinition, AgentMode, SkillDefinition } from '@/types/studio'

export type OpenCodeHarnessPack = {
  agents?: AgentDefinition[]
  skills?: SkillDefinition[]
  commands?: Array<Record<string, unknown>>
  mcp?: Record<string, Record<string, unknown> | null>
  plugin?: string[]
  marketplace_items?: Array<Record<string, unknown>>
  remove_agents?: string[]
  remove_skills?: string[]
  remove_commands?: string[]
  remove_plugins?: string[]
  remove_marketplace_items?: Array<Record<string, unknown>>
  replace_all_agents?: boolean
  replace_all_skills?: boolean
  replace_all_commands?: boolean
  model?: string
  small_model?: string
  default_agent?: string
  manifest?: Record<string, unknown>
  agent_meta?: Record<string, unknown>
}

export type OpenCodeHarnessResponse = {
  sandbox_name: string
  agents: Array<Record<string, unknown>>
  skills: Array<Record<string, unknown>>
  commands?: Array<Record<string, unknown>>
  plugins?: string[]
  mcp: Record<string, Record<string, unknown>>
  manifest: Record<string, unknown>
  opencode_json?: Record<string, unknown>
  written?: {
    agents?: string[]
    skills?: string[]
    commands?: string[]
    plugins?: string[]
    removed_agents?: string[]
    removed_skills?: string[]
    removed_commands?: string[]
    removed_plugins?: string[]
  }
}

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/

export function isValidAgentSlug(name: string): boolean {
  return SLUG_RE.test(name) && name.length >= 1 && name.length <= 64
}

/** Convert free text to OpenCode-safe slug. */
export function slugifyAgentName(input: string): string {
  const s = input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/--+/g, '-')
    .slice(0, 64)
  return s || 'agent'
}

export function agentFromPack(raw: Record<string, unknown>): AgentDefinition {
  const id = String(raw.id || raw.name || '')
  const description = String(raw.description || raw.desc || '')
  const prompt = String(raw.prompt || raw.systemPrompt || '')
  const mode = (raw.mode as AgentMode) || 'all'
  return {
    id,
    name: id,
    description,
    desc: description,
    prompt,
    systemPrompt: prompt,
    mode,
    model: raw.model ? String(raw.model) : undefined,
    modelsPreferred: Array.isArray(raw.modelsPreferred)
      ? (raw.modelsPreferred as string[]).map(String)
      : Array.isArray(raw.models_preferred)
        ? (raw.models_preferred as string[]).map(String)
        : undefined,
    permission: (raw.permission as AgentDefinition['permission']) || undefined,
    mcpIds: Array.isArray(raw.mcpIds)
      ? (raw.mcpIds as string[]).map(String)
      : Array.isArray(raw.mcp_ids)
        ? (raw.mcp_ids as string[]).map(String)
        : undefined,
    skillAllow: Array.isArray(raw.skillAllow)
      ? (raw.skillAllow as string[]).map(String)
      : Array.isArray(raw.skill_allow)
        ? (raw.skill_allow as string[]).map(String)
        : undefined,
    color: raw.color ? String(raw.color) : undefined,
    temperature: typeof raw.temperature === 'number' ? raw.temperature : undefined,
    disable: raw.disable === true,
    managed: raw.managed !== false,
    source: (raw.source as AgentDefinition['source']) || 'opencode-file',
    active: true,
    tools: [],
    role: mode,
  }
}

export function skillFromPack(raw: Record<string, unknown>): SkillDefinition {
  const id = String(raw.id || raw.name || '')
  return {
    id,
    name: String(raw.name || id),
    description: String(raw.description || ''),
    body: String(raw.body || raw.prompt || ''),
    managed: raw.managed !== false,
    source: (raw.source as SkillDefinition['source']) || 'opencode-file',
  }
}

export function agentToPackPayload(agent: AgentDefinition): Record<string, unknown> {
  const id = slugifyAgentName(agent.id || agent.name)
  return {
    id,
    description: agent.description || agent.desc || `Agent ${id}`,
    mode: agent.mode || 'all',
    model: agent.model || undefined,
    prompt: agent.prompt || agent.systemPrompt || '',
    permission: agent.permission || undefined,
    modelsPreferred: agent.modelsPreferred || undefined,
    mcpIds: agent.mcpIds || undefined,
    skillAllow: agent.skillAllow || undefined,
    color: agent.color || undefined,
    temperature: agent.temperature,
    disable: agent.disable || undefined,
  }
}

export function skillToPackPayload(skill: SkillDefinition): Record<string, unknown> {
  const id = slugifyAgentName(skill.id || skill.name)
  return {
    id,
    name: id,
    description: skill.description || `Skill ${id}`,
    body: skill.body || '',
  }
}

export async function getOpenCodeHarness(projectId: string): Promise<OpenCodeHarnessResponse> {
  return apiFetch(`/api/v1/projects/${projectId}/harness/opencode`)
}

export async function putOpenCodeHarness(
  projectId: string,
  pack: OpenCodeHarnessPack,
): Promise<OpenCodeHarnessResponse> {
  return apiFetch(`/api/v1/projects/${projectId}/harness/opencode`, {
    method: 'PUT',
    body: JSON.stringify(pack),
  })
}

/** Built-in OpenCode agents shown as read-only when live list includes them. */
export const OPENCODE_BUILTIN_AGENTS = new Set([
  'build',
  'plan',
  'general',
  'explore',
  'scout',
  'compaction',
  'title',
  'summary',
])

/**
 * Platform-injected MCP servers. Listed under System in Tools (not counted as
 * user MCP servers, not deletable); users can still deny them per prompt in chat.
 */
export const SYSTEM_MCP_SERVERS = new Set(['everflow'])

export function isSystemMcp(nameOrId: string): boolean {
  return SYSTEM_MCP_SERVERS.has(nameOrId.trim().toLowerCase())
}

/** Common OpenCode permission keys for the agent form. */
export const OPENCODE_TOOL_PERMISSIONS: {
  id: string
  label: string
  description: string
}[] = [
  { id: 'read', label: 'Read files', description: 'read tool' },
  { id: 'edit', label: 'Edit / write', description: 'write, edit, apply_patch' },
  { id: 'bash', label: 'Shell', description: 'bash commands' },
  { id: 'glob', label: 'Glob', description: 'find files by pattern' },
  { id: 'grep', label: 'Grep', description: 'search code' },
  { id: 'webfetch', label: 'Web fetch', description: 'fetch URLs' },
  { id: 'websearch', label: 'Web search', description: 'search the web' },
  { id: 'task', label: 'Task / subagents', description: 'spawn subagents' },
  { id: 'skill', label: 'Skills', description: 'load skill packs' },
  { id: 'question', label: 'Questions', description: 'ask the user' },
]
