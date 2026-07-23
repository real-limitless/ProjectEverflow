/**
 * Map Everflow chat modes (Ask / Edit only / Automatic) onto OpenCode
 * per-prompt tools + permission policy.
 *
 * Modes are permission levels only — agent selection is independent
 * (composer primary agent). Prefer per-prompt settings over mutating
 * sandbox-wide opencode.json so mode switches stay isolated to the next message.
 */

import type { ChatMode } from '@/types/panels'

export type OpenCodeModePrompt = {
  /** Legacy tools boolean map — false denies the tool. */
  tools?: Record<string, boolean>
  /** When true, the UI auto-replies to permission SSE with "once". */
  autoApprovePermissions: boolean
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
export function openCodePromptForMode(mode: ChatMode): OpenCodeModePrompt {
  if (mode === 'ask') {
    return {
      tools: {
        ...DENY_EDIT,
        ...DENY_BASH,
      },
      autoApprovePermissions: false,
    }
  }

  if (mode === 'edit') {
    return {
      tools: {
        ...DENY_BASH,
      },
      autoApprovePermissions: false,
    }
  }

  // auto
  return {
    tools: undefined,
    autoApprovePermissions: true,
  }
}

/** Human-readable short label for mode policy (UI hints). */
export function modePolicyHint(mode: ChatMode): string {
  switch (mode) {
    case 'ask':
      return 'Read-only — no edits or shell'
    case 'edit':
      return 'Edits with approval; no shell'
    case 'auto':
      return 'Edits & commands auto-approved'
    default:
      return ''
  }
}
