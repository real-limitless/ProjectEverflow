import type { ChatConversation, ChatMessage } from './panels'

export type RepoProvider = 'github' | 'gitlab' | 'other' | 'none'

export type RepoCloneStatus = 'pending' | 'cloning' | 'ready' | 'skipped' | 'error' | string

export interface ProjectRepo {
  id: string
  label: string
  active: boolean
  url?: string
  branch?: string
  provider?: RepoProvider
  /** Workspace-relative git root (e.g. "." or "web"). Resolved at runtime when omitted. */
  localPath?: string
  /** Server/UI clone lifecycle for remotes into the sandbox workspace */
  cloneStatus?: RepoCloneStatus
  cloneError?: string
}

export interface ProjectHarness {
  id: string
  label: string
  enabled: boolean
}

export type WorkspaceLayoutMode = 'standard' | 'chat-first' | 'code-first'

export type ProjectVisibility = 'private' | 'public'

export type ProjectEnvironment = 'local' | 'staging' | 'production-stub'

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

/** Git working-tree status for a path (from Repository → Changes). */
export type GitChangeStatus = 'M' | 'A' | 'D' | 'R' | 'U'

export interface GitFileChange {
  path: string
  status: GitChangeStatus
  /** Lines added vs base (e.g. HEAD) */
  additions: number
  /** Lines deleted vs base */
  deletions: number
  /** Optional unified diff preview for Repository panel */
  diffPreview?: string
  /** Display name override (defaults to basename of path) */
  label?: string
}

export type SandboxLifecycleStatus =
  | 'pending'
  | 'creating'
  | 'running'
  | 'stopped'
  | 'error'
  | 'destroyed'
  | string

export interface Project {
  id: string
  name: string
  description?: string
  slug?: string
  templateId?: string
  /** Preview device frame id (see devicePresets). */
  previewDevice?: string
  harnesses?: ProjectHarness[]
  layoutMode?: WorkspaceLayoutMode
  environment?: ProjectEnvironment
  visibility?: ProjectVisibility
  /** API-backed project (UUID); false for pure local demo seeds */
  fromApi?: boolean
  organizationId?: string
  sandboxName?: string | null
  sandboxStatus?: SandboxLifecycleStatus
  sandboxImage?: string | null
  sandboxError?: string | null
  sandboxCreatedAt?: string | null
  repos: ProjectRepo[]
  convs: ProjectConv[]
  /** @deprecated Prefer per-conversation messages; kept for seed simplicity */
  messages: ChatMessage[]
  /** Optional full conversation seeds (preferred) */
  conversations?: ChatConversation[]
  files: ProjectFile[]
  code: Record<string, string>
  /** Working-tree changes surfaced in Code tree + Repository panel */
  gitChanges?: GitFileChange[]
  knowledgeFiles: { name: string; path: string }[]
  canvases: { name: string; desc: string }[]
  termLines: { cls: string; text: string }[]
}

export type PaletteMode = 'float' | 'docked' | 'chip'
