/** Minimal OpenCode wire types (defensive; schema may drift). */

export type OcPart = {
  type: string
  text?: string
  content?: string
  id?: string
  tool?: string
  name?: string
  title?: string
  state?: string | { status?: string; output?: string; error?: string }
  input?: unknown
  output?: unknown
  callID?: string
  // question
  question?: string
  header?: string
  options?: Array<string | { label?: string; value?: string }>
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

export type OcMessageInfo = {
  id: string
  role: string
  agent?: string
  model?: { providerID?: string; modelID?: string }
  time?: { created?: number; completed?: number }
  error?: { name?: string; message?: string }
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
