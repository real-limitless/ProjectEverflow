import type { ChatMessage } from './panels'

export interface ProjectRepo {
  id: string
  label: string
  active: boolean
}

export interface ProjectConv {
  id: string
  title: string
  meta: string
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
  messages: ChatMessage[]
  files: ProjectFile[]
  code: Record<string, string>
  knowledgeFiles: { name: string; path: string }[]
  canvases: { name: string; desc: string }[]
  termLines: { cls: string; text: string }[]
}

export type PaletteMode = 'float' | 'docked' | 'chip'
