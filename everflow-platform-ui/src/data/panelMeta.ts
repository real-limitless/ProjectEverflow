import type { PanelMeta, PanelType } from '@/types/panels'

export const PANEL_META: Record<PanelType, PanelMeta> = {
  chat: { label: 'Chat', icon: '💬' },
  preview: { label: 'Preview', icon: '▣' },
  desktop: { label: 'Desktop', icon: '🖥' },
  knowledge: { label: 'Knowledge', icon: '📚' },
  code: { label: 'Code', icon: '</>' },
  repository: { label: 'Repository', icon: '⌥' },
  terminal: { label: 'Terminal', icon: '>_' },
  workflows: { label: 'Workflows', icon: '🔀' },
  database: { label: 'Database', icon: '🗄' },
  jobs: { label: 'Jobs', icon: '⏱' },
  agents: { label: 'Agent / Skills', icon: '🤖' },
  tools: { label: 'Tools / MCPs / Plugins', icon: '🔌' },
  env: { label: 'Env / Secrets', icon: '🔐' },
  tests: { label: 'Tests', icon: '✓' },
  deploy: { label: 'Deploy', icon: '🚀' },
}
