import {
  catalogReposToWorkspace,
  parseDiffStats,
  parseGitLog,
  parseGitStatusPorcelain,
  pathHintFromLabel,
  prefixChanges,
  sanitizeBranchName,
  sanitizeRepoPath,
  statusCodeFromPorcelain,
  workspaceRelativePath,
} from './workspaceGit'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

assert(sanitizeRepoPath('../etc') === '.', 'reject ..')
assert(sanitizeRepoPath('web/src') === 'web/src', 'allow nested')
assert(sanitizeRepoPath('./api') === 'api', 'strip ./')
assert(pathHintFromLabel('aura-host/web') === 'web', 'label basename')
assert(pathHintFromLabel('https://github.com/org/app.git') === 'app', 'url basename')

const porcelain = [
  ' M src/a.ts',
  'A  src/new.ts',
  'D  old.ts',
  '?? untracked.md',
  'R  from.ts -> to.ts',
].join('\n')
const changes = parseGitStatusPorcelain(porcelain)
assert(changes.length === 5, '5 status lines')
assert(changes[0].status === 'M' && changes[0].path === 'src/a.ts', 'modified')
assert(changes[1].status === 'A' && changes[1].path === 'src/new.ts', 'added')
assert(changes[2].status === 'D', 'deleted')
assert(changes[3].status === 'A' && changes[3].path === 'untracked.md', 'untracked as A')
assert(changes[4].status === 'R' && changes[4].path === 'to.ts', 'rename target')

assert(statusCodeFromPorcelain('M ') === 'M', 'index M')
assert(statusCodeFromPorcelain('??') === 'A', 'untracked')

const stats = parseDiffStats('+a\n+b\n-c\n line\n+++ header\n--- header\n')
assert(stats.additions === 2 && stats.deletions === 1, 'diff stats')

const logRaw =
  '\x1e' +
  [
    'aaa111',
    'aaa1111',
    'Fix thing',
    'you',
    '2m ago',
    'bbb222',
    'HEAD -> main, origin/main',
  ].join('\x1f') +
  '\x1e' +
  ['bbb222', 'bbb2222', 'Init', 'rafi', '1w ago', '', 'main'].join('\x1f')
const commits = parseGitLog(logRaw)
assert(commits.length === 2, '2 commits')
assert(commits[0].message === 'Fix thing', 'message')
assert(commits[0].isHead === true, 'HEAD')
assert(commits[0].parents[0] === 'bbb222', 'parent')

assert(workspaceRelativePath('.', 'src/a.ts') === 'src/a.ts', 'root rel')
assert(workspaceRelativePath('web', 'src/a.ts') === 'web/src/a.ts', 'prefix')
const pref = prefixChanges([{ path: 'x.ts', status: 'M', additions: 1, deletions: 0 }], 'api')
assert(pref[0].path === 'api/x.ts', 'prefix changes')

const cat = catalogReposToWorkspace([
  { id: 'web', label: 'org/web', active: true },
  { id: 'api', label: 'org/api', active: false },
])
assert(cat.length === 2, '2 catalog')
assert(cat[0].path === 'web' || cat[0].path === 'org', 'multi path hint')
const single = catalogReposToWorkspace([{ id: 'main', label: 'app', active: true }])
assert(single[0].path === '.', 'single defaults to .')

assert(sanitizeBranchName('main') === 'main', 'branch main')
assert(sanitizeBranchName('feature/foo-bar') === 'feature/foo-bar', 'branch slash')
assert(sanitizeBranchName('../etc') === null, 'reject .. branch')
assert(sanitizeBranchName('-bad') === null, 'reject leading dash')
assert(sanitizeBranchName('a;rm') === null, 'reject metachar')
assert(sanitizeBranchName('origin/main') === 'origin/main', 'remote ref')

console.log('workspaceGit.selftest: ok')
