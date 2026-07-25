/**
 * Run: npx tsx src/lib/opencode/chatMode.selftest.ts
 */
import { mcpToolsDenyMap, modePolicyHint, openCodePromptForMode } from './chatMode'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

// --- Ask strict ---
const ask = openCodePromptForMode('ask')
assert(ask.autoApprovePermissions === false, 'ask does not auto-approve')
assert(ask.tools?.edit === false, 'ask denies edit')
assert(ask.tools?.write === false, 'ask denies write')
assert(ask.tools?.bash === false, 'ask denies bash')
assert(!('agent' in ask), 'mode must not set agent')

// --- Ask soft ---
const askSoft = openCodePromptForMode('ask', { softPermissions: true })
assert(askSoft.autoApprovePermissions === false, 'soft ask never auto-approves')
assert(askSoft.tools === undefined, 'soft ask does not hard-deny tools')

// --- Edit strict ---
const edit = openCodePromptForMode('edit')
assert(edit.autoApprovePermissions === false, 'edit does not auto-approve')
assert(edit.tools?.bash === false, 'edit denies bash')
assert(edit.tools?.edit !== false, 'edit allows edit (not denied)')
assert(!('agent' in edit), 'edit mode must not set agent')

// --- Edit soft ---
const editSoft = openCodePromptForMode('edit', { softPermissions: true })
assert(editSoft.autoApprovePermissions === false, 'soft edit never auto-approves')
assert(editSoft.tools === undefined, 'soft edit allows shell (no deny map)')

// --- Auto (soft ignored) ---
const auto = openCodePromptForMode('auto')
assert(auto.autoApprovePermissions === true, 'auto auto-approves')
assert(auto.tools === undefined, 'auto leaves tools unrestricted')

const autoSoft = openCodePromptForMode('auto', { softPermissions: true })
assert(autoSoft.autoApprovePermissions === true, 'auto soft still auto-approves')
assert(autoSoft.tools === undefined, 'auto soft unrestricted')

// Hints
assert(modePolicyHint('ask').toLowerCase().includes('read'), 'ask hint')
assert(modePolicyHint('edit').toLowerCase().includes('edit'), 'edit hint')
assert(modePolicyHint('auto').toLowerCase().includes('auto'), 'auto hint')
assert(
  modePolicyHint('ask', true).toLowerCase().includes('approve'),
  'soft ask hint',
)

// --- MCP deny map ---
const deny = mcpToolsDenyMap(['everflow', 'github', 'slack'], ['everflow'])
assert(deny['github_*'] === false, 'denies unchecked github')
assert(deny['slack_*'] === false, 'denies unchecked slack')
assert(deny['everflow_*'] === undefined, 'does not deny checked everflow')
assert(Object.keys(mcpToolsDenyMap(['everflow'], ['everflow'])).length === 0, 'all enabled → empty')

console.log('chatMode.selftest: ok')
