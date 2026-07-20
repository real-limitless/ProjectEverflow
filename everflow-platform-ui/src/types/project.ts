import type { ChatConversation, ChatMessage } from './panels'

export interface ProjectRepo {
  id: string
  label: string
  active: boolean
}

export interface ProjectConv {
  id: string
  title: string
  meta: string
  pinned?: boolean
  /** Per-conversation messages when set; else fall back to project.messages for primary */
  messages?: ChatMessage[]
}

export interface ProjectFile {
  path: string
  name: string
  folder: string
}

export interface Project {
  id: string
  name: string
  repos: ProjectRepo[]
  convs: ProjectConv[]
  /** @deprecated Prefer per-conversation messages; kept for seed simplicity */
  messages: ChatMessage[]
  /** Optional full conversation seeds (preferred) */
  conversations?: ChatConversation[]
  files: ProjectFile[]
  code: Record<string, string>
  knowledgeFiles: { name: string; path: string }[]
  canvases: { name: string; desc: string }[]
  termLines: { cls: string; text: string }[]
}

export type PaletteMode = 'float' | 'docked' | 'chip'
