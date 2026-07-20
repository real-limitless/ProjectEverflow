import type { AgentRole, ChatAgentRef, ChatMode } from '@/types/panels'

export interface CatalogItem {
  id: string
  label: string
  description?: string
}

export const CHAT_MODELS: CatalogItem[] = [
  { id: 'grok-2', label: 'Grok 2', description: 'xAI' },
  { id: 'gpt-4.1', label: 'GPT-4.1', description: 'OpenAI' },
  { id: 'claude-sonnet', label: 'Claude Sonnet', description: 'Anthropic' },
  { id: 'ollama/llama3', label: 'Llama 3 (local)', description: 'Ollama' },
]

export const CHAT_TOOLS: CatalogItem[] = [
  { id: 'sandbox_fs', label: 'Sandbox FS', description: 'Read/write project files' },
  { id: 'git', label: 'Git', description: 'Status, diff, commit' },
  { id: 'web_search', label: 'Web search', description: 'Approved search' },
  { id: 'terminal', label: 'Terminal', description: 'Run sandbox commands' },
  { id: 'deploy', label: 'Deploy', description: 'Preview / staging deploys' },
]

export const CHAT_MCPS: CatalogItem[] = [
  { id: 'github-mcp', label: 'GitHub MCP', description: 'Issues, PRs, repos' },
  { id: 'docs-search', label: 'Docs search', description: 'Internal docs RAG' },
  { id: 'postgres-mcp', label: 'Postgres MCP', description: 'SQL tools' },
  { id: 'slack-mcp', label: 'Slack MCP', description: 'Notify channels' },
]

export const CHAT_SKILLS: CatalogItem[] = [
  { id: 'fix', label: '/fix', description: 'Diagnose and patch bugs' },
  { id: 'commit', label: '/commit', description: 'Write commit messages' },
  { id: 'review-pr', label: '/review-pr', description: 'Review pull requests' },
  { id: 'explain', label: '/explain', description: 'Explain code clearly' },
]

export const CHAT_MODES: { id: ChatMode; label: string; description: string }[] = [
  { id: 'ask', label: 'Ask', description: 'Answer only — no file edits' },
  { id: 'edit', label: 'Edit only', description: 'Propose and apply code edits' },
  { id: 'auto', label: 'Automatic', description: 'Full agent workflow with tools' },
]

export const CHAT_AGENTS: ChatAgentRef[] = [
  { id: 'planner', name: 'Planner', role: 'planner' },
  { id: 'architect', name: 'Architect', role: 'architect' },
  { id: 'frontend', name: 'Frontend', role: 'frontend' },
  { id: 'backend', name: 'Backend', role: 'backend' },
  { id: 'general', name: 'General', role: 'general' },
]

export const DEFAULT_CHAT_MODEL = 'grok-2'
export const DEFAULT_CHAT_TOOLS = ['sandbox_fs', 'git']
export const DEFAULT_CHAT_MCPS = ['github-mcp']
export const DEFAULT_CHAT_SKILLS = ['fix']
export const DEFAULT_CHAT_AGENTS = ['planner', 'frontend', 'backend']
export const DEFAULT_CHAT_MODE: ChatMode = 'ask'
export const DEFAULT_CONTEXT_WINDOW = 128_000

export function agentById(id: string): ChatAgentRef {
  return CHAT_AGENTS.find((a) => a.id === id) || { id, name: id, role: 'general' as AgentRole }
}

export function modeLabel(mode: ChatMode | undefined): string {
  return CHAT_MODES.find((m) => m.id === mode)?.label || 'Ask'
}
