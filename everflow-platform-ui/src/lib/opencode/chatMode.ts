/**
 * Map Everflow chat modes (Ask / Edit only / Automatic) onto OpenCode
 * per-prompt tools + permission policy.
 *
 * Modes are permission levels only — agent selection is independent
 * (composer primary agent). Prefer per-prompt settings over mutating
 * sandbox-wide opencode.json so mode switches stay isolated to the next message.
 *
 * Strict (default): hard-deny tools via tools map (no permission popup for denied tools).
 * Soft (`softPermissions`): allow tools; UI never auto-approves — user gets Allow once/Always/Deny.
 */

import type { ChatMode } from '@/types/panels'

export type OpenCodeModePrompt = {
  /** Legacy tools boolean map — false denies the tool. */
  tools?: Record<string, boolean>
  /** When true, the UI auto-replies to permission SSE with "once". */
  autoApprovePermissions: boolean
}

export type OpenCodeModeOptions = {
  /**
   * Ask/Edit only. When true, skip hard tool denies and require interactive
   * permission cards for sensitive tools (edit/shell).
   */
  softPermissions?: boolean
}

const DENY_EDIT = {
  edit: false,
  write: false,
  apply_patch: false,
  patch: false,
} as const

const DENY_BASH = {
  bash: false,
  shell: false,
} as const

/**
 * Build OpenCode prompt options for a chat permission mode.
 * Does not pick an agent — caller supplies agent separately.
 */
export function openCodePromptForMode(
  mode: ChatMode,
  opts?: OpenCodeModeOptions,
): OpenCodeModePrompt {
  const soft = Boolean(opts?.softPermissions)

  // Auto is always full power + auto-approve (soft toggle ignored).
  if (mode === 'auto') {
    return {
      tools: undefined,
      autoApprovePermissions: true,
    }
  }

  // Soft Ask/Edit: do not hard-deny; never auto-approve.
  if (soft) {
    return {
      tools: undefined,
      autoApprovePermissions: false,
    }
  }

  if (mode === 'ask') {
    return {
      tools: {
        ...DENY_EDIT,
        ...DENY_BASH,
      },
      autoApprovePermissions: false,
    }
  }

  // edit (strict)
  return {
    tools: {
      ...DENY_BASH,
    },
    autoApprovePermissions: false,
  }
}

/** Human-readable short label for mode policy (UI hints). */
export function modePolicyHint(mode: ChatMode, softPermissions?: boolean): string {
  if (mode === 'auto') {
    return 'Edits & commands auto-approved'
  }
  if (softPermissions) {
    if (mode === 'ask') {
      return 'Tools allowed only after you approve each request'
    }
    return 'Edits & shell after approval'
  }
  switch (mode) {
    case 'ask':
      return 'Read-only — no edits or shell'
    case 'edit':
      return 'Edits with approval; no shell'
    default:
      return ''
  }
}

/**
 * Best-effort per-prompt MCP filter for OpenCode `tools` map.
 * Unchecked servers are denied via `{server}_*` wildcards (same pattern as
 * agent harness permissions). Checked servers inherit agent/harness allow rules.
 */
export function mcpToolsDenyMap(
  liveMcpIds: string[],
  enabledMcpIds: string[],
): Record<string, boolean> {
  const enabled = new Set(enabledMcpIds)
  const out: Record<string, boolean> = {}
  for (const id of liveMcpIds) {
    if (!id || enabled.has(id)) continue
    out[`${id}_*`] = false
  }
  return out
}
