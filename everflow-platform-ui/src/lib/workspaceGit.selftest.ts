import {
  catalogReposToWorkspace,
  isEverflowWorktreePath,
  parseDiffStats,
  parseGitLog,
  parseGitStatusPorcelain,
  parseWorktreeIndexJson,
  parseWorktreePorcelain,
  pathHintFromLabel,
  planApproveMergeCommands,
  planDiscardWorktreeCommands,
  prefixChanges,
  sanitizeBranchName,
  sanitizeRepoPath,
  sanitizeWorktreeRepoId,
  sanitizeWorktreeSessionId,
  statusCodeFromPorcelain,
  worktreeBranchForSession,
  worktreePathForSession,
  worktreeSystemPrompt,
  workspaceRelFromAbsPath,
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
assert(cat.every((r) => r.hasGit === false), 'catalog defaults hasGit false')
// Multi-repo path hints must not invent a bare "test" root unless the label basename is test
const withTestLabel = catalogReposToWorkspace([
  { id: 'main', label: 'org/app', active: true },
  { id: 'extra', label: 'test', active: false },
])
assert(withTestLabel[1].path === 'test', 'label test → path test')
assert(withTestLabel[1].label === 'test', 'label preserved')
assert(withTestLabel[1].hasGit === false, 'no git until live probe')
const single = catalogReposToWorkspace([{ id: 'main', label: 'app', active: true }])
assert(single[0].path === 'app', 'single uses label basename as path')
const withUrl = catalogReposToWorkspace([
  {
    id: 'r1',
    label: 'repo-1',
    active: true,
    url: 'https://github.com/org/my-app.git',
    localPath: '.',
  },
])
assert(withUrl[0].path === 'my-app', 'URL basename even when localPath was .')
assert(withUrl[0].path !== '.', 'remotes never map to workspace root')

assert(sanitizeBranchName('main') === 'main', 'branch main')
assert(sanitizeBranchName('feature/foo-bar') === 'feature/foo-bar', 'branch slash')
assert(sanitizeBranchName('../etc') === null, 'reject .. branch')
assert(sanitizeBranchName('-bad') === null, 'reject leading dash')
assert(sanitizeBranchName('a;rm') === null, 'reject metachar')
assert(sanitizeBranchName('origin/main') === 'origin/main', 'remote ref')

// Worktree helpers
assert(isEverflowWorktreePath('.everflow/worktrees/web/ses_abc'), 'wt path')
assert(!isEverflowWorktreePath('web'), 'not wt path')
assert(sanitizeWorktreeSessionId('ses_abc-123') === 'ses_abc-123', 'session id')
assert(sanitizeWorktreeSessionId('../x') === null, 'reject bad session')
assert(sanitizeWorktreeRepoId('org/web') === 'org-web', 'repo id flatten')
assert(worktreePathForSession('web', 'ses_hello') === '.everflow/worktrees/web/ses_hello', 'wt path build')
assert(worktreeBranchForSession('ses_abcdef0123456789') === 'ef/abcdef0123456789', 'branch short')
assert(workspaceRelFromAbsPath('/workspace/.everflow/worktrees/web/s1') === '.everflow/worktrees/web/s1', 'abs→rel')
assert(workspaceRelFromAbsPath('/workspace') === '.', 'workspace root')

const porcelainWt = [
  'worktree /workspace/web',
  'HEAD abc',
  'branch refs/heads/main',
  '',
  'worktree /workspace/.everflow/worktrees/web/ses_1',
  'HEAD def',
  'branch refs/heads/ef/1',
  '',
].join('\n')
const wtEntries = parseWorktreePorcelain(porcelainWt)
assert(wtEntries.length === 2, '2 worktrees')
assert(wtEntries[0].path === 'web' && wtEntries[0].branch === 'main', 'main entry')
assert(
  wtEntries[1].path === '.everflow/worktrees/web/ses_1' && wtEntries[1].branch === 'ef/1',
  'isolated entry',
)

const discardPlan = planDiscardWorktreeCommands('.everflow/worktrees/web/ses_1', 'ef/1')
assert(discardPlan.length === 2, 'discard 2 cmds')
assert(discardPlan[0][0] === 'worktree' && discardPlan[0].includes('--force'), 'remove force')
assert(discardPlan[1][0] === 'branch' && discardPlan[1][1] === '-D', 'branch -D')

const approvePlan = planApproveMergeCommands('ef/1')
assert(approvePlan[0][0] === 'merge' && approvePlan[0].includes('ef/1'), 'merge branch')
assert(approvePlan.some((c) => c[0] === 'branch' && c[1] === '-D'), 'delete after merge')

const idx = parseWorktreeIndexJson(
  JSON.stringify({
    entries: [
      {
        sessionId: 'ses_1',
        repoId: 'web',
        parentPath: 'web',
        path: '.everflow/worktrees/web/ses_1',
        branch: 'ef/1',
        status: 'active',
      },
      { sessionId: 'bad' },
    ],
  }),
)
assert(idx.entries.length === 1, 'index filters bad rows')
assert(idx.entries[0].status === 'active', 'index status')

const sys = worktreeSystemPrompt('.everflow/worktrees/web/ses_1', 'web')
assert(sys.includes('/workspace/.everflow/worktrees/web/ses_1'), 'system wt path')
assert(sys.includes('/workspace/web'), 'system parent path')

console.log('workspaceGit.selftest: ok')
