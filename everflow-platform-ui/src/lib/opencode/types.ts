/** Minimal OpenCode wire types (defensive; schema may drift). */

export type OcToolState = {
  status?: string
  input?: Record<string, unknown>
  output?: string
  error?: string
  title?: string
  metadata?: Record<string, unknown>
  raw?: string
  time?: { start?: number; end?: number }
}

export type OcPart = {
  type: string
  text?: string
  content?: string
  id?: string
  sessionID?: string
  messageID?: string
  tool?: string
  name?: string
  title?: string
  state?: string | OcToolState
  input?: unknown
  output?: unknown
  callID?: string
  // question (rare as part; usually SSE question.asked)
  question?: string
  header?: string
  options?: Array<string | { label?: string; value?: string; description?: string }>
  questions?: OcQuestionInfo[]
  // permission
  permission?: string
  permissionID?: string
  patterns?: string[]
  // file / terminal-ish
  path?: string
  command?: string
  exit?: number
  filename?: string
  mime?: string
  url?: string
  [key: string]: unknown
}

export type OcQuestionOption = {
  label: string
  description?: string
}

export type OcQuestionInfo = {
  question: string
  header?: string
  options?: OcQuestionOption[]
  multiple?: boolean
  custom?: boolean
}

export type OcQuestionRequest = {
  id: string
  sessionID?: string
  questions: OcQuestionInfo[]
  tool?: { messageID?: string; callID?: string }
}

export type OcMessageInfo = {
  id: string
  role: string
  agent?: string
  model?: { providerID?: string; modelID?: string }
  time?: { created?: number; completed?: number }
  /** Present when generation finished (e.g. "stop") */
  finish?: string
  tokens?: {
    total?: number
    input?: number
    output?: number
    reasoning?: number
    cache?: { read?: number; write?: number }
  }
  error?: { name?: string; message?: string } | string
  [key: string]: unknown
}

export type OcMessageBundle = {
  info: OcMessageInfo
  parts: OcPart[]
}

export type OcSession = {
  id: string
  title?: string
  parentID?: string
  time?: { created?: number; updated?: number }
  [key: string]: unknown
}

export type OcProvider = {
  id: string
  name?: string
  models?: Record<string, { id?: string; name?: string }> | Array<{ id: string; name?: string }>
  [key: string]: unknown
}

export type OcAgent = {
  name: string
  mode?: string
  description?: string
  [key: string]: unknown
}

export type OcMcpStatus = {
  status?: string
  error?: string
  [key: string]: unknown
}

export type OcEnsureResult = {
  sandbox_name: string
  healthy: boolean
  port?: number
  base_url?: string
  version?: string
  mode?: string
  error?: string
}

export type OcEvent = {
  type: string
  properties?: Record<string, unknown>
  [key: string]: unknown
}
