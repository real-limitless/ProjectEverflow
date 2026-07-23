/**
 * Run: npx tsx src/lib/workspaceRepos.selftest.ts
 */
import {
  isCloneableUrl,
  normalizeReposForCreate,
  projectReposToApiPayload,
} from './workspaceRepos'
import { pathHintFromLabel } from './workspaceGit'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

assert(isCloneableUrl('https://github.com/a/b.git'), 'https cloneable')
assert(isCloneableUrl('git@github.com:a/b.git'), 'ssh cloneable')
assert(!isCloneableUrl(''), 'empty not cloneable')
assert(!isCloneableUrl('foo'), 'plain not cloneable')

assert(pathHintFromLabel('https://github.com/org/app.git') === 'app', 'url basename')

const single = normalizeReposForCreate([
  {
    id: 'r1',
    label: 'app',
    active: true,
    url: 'https://github.com/org/app.git',
    branch: 'main',
    provider: 'github',
  },
])
assert(single[0].localPath === 'app', 'single remote uses named dir')
assert(single[0].localPath !== '.', 'never workspace root')
assert(single[0].cloneStatus === 'pending', 'pending clone')

const multi = normalizeReposForCreate([
  {
    id: 'a',
    label: 'frontend',
    active: true,
    url: 'https://github.com/org/frontend.git',
    provider: 'github',
  },
  {
    id: 'b',
    label: 'backend',
    active: false,
    url: 'https://github.com/org/backend.git',
    provider: 'github',
  },
])
assert(multi[0].localPath === 'frontend', 'multi first is frontend')
assert(multi[1].localPath === 'backend', 'multi second is backend')
assert(multi[0].localPath !== '.', 'multi not root')
assert(multi.filter((r) => r.active).length === 1, 'one active')

const payload = projectReposToApiPayload(single)
assert(payload[0].url?.includes('github.com'), 'api payload has url')
assert(payload[0].local_path === 'app', 'api local_path is named dir')

console.log('workspaceRepos.selftest: ok')
