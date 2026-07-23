/**
 * Run: npx tsx src/lib/opencode/chatMode.selftest.ts
 */
import { mcpToolsDenyMap, modePolicyHint, openCodePromptForMode } from './chatMode'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

// --- Ask ---
const ask = openCodePromptForMode('ask')
assert(ask.autoApprovePermissions === false, 'ask does not auto-approve')
assert(ask.tools?.edit === false, 'ask denies edit')
assert(ask.tools?.write === false, 'ask denies write')
assert(ask.tools?.bash === false, 'ask denies bash')
assert(!('agent' in ask), 'mode must not set agent')

// --- Edit ---
const edit = openCodePromptForMode('edit')
assert(edit.autoApprovePermissions === false, 'edit does not auto-approve')
assert(edit.tools?.bash === false, 'edit denies bash')
assert(edit.tools?.edit !== false, 'edit allows edit (not denied)')
assert(!('agent' in edit), 'edit mode must not set agent')

// --- Auto ---
const auto = openCodePromptForMode('auto')
assert(auto.autoApprovePermissions === true, 'auto auto-approves')
assert(auto.tools === undefined, 'auto leaves tools unrestricted')
assert(!('agent' in auto), 'auto mode must not set agent')

// Hints
assert(modePolicyHint('ask').toLowerCase().includes('read'), 'ask hint')
assert(modePolicyHint('edit').toLowerCase().includes('edit'), 'edit hint')
assert(modePolicyHint('auto').toLowerCase().includes('auto'), 'auto hint')

// --- MCP deny map ---
const deny = mcpToolsDenyMap(['everflow', 'github', 'slack'], ['everflow'])
assert(deny['github_*'] === false, 'denies unchecked github')
assert(deny['slack_*'] === false, 'denies unchecked slack')
assert(deny['everflow_*'] === undefined, 'does not deny checked everflow')
assert(Object.keys(mcpToolsDenyMap(['everflow'], ['everflow'])).length === 0, 'all enabled → empty')

console.log('chatMode.selftest: ok')
