import { buildFileTree, dirsContainingPaths, basename } from './fileTree'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

const files = [
  { path: 'src/pages/Index.tsx', name: 'Index.tsx', folder: 'pages' },
  { path: 'src/components/dashboard/MetricCard.tsx', name: 'MetricCard.tsx', folder: 'dashboard' },
  { path: 'src/App.tsx', name: 'App.tsx', folder: 'src' },
  { path: 'README.md', name: 'README.md', folder: '' },
]

const tree = buildFileTree(files)
assert(tree.length === 2, 'root should have src + README')
assert(tree[0].kind === 'dir' && tree[0].name === 'src', 'dirs first, sorted')
assert(tree[1].kind === 'file' && tree[1].name === 'README.md', 'file at root')

const src = tree[0]
assert(src.kind === 'dir', 'src is dir')
assert(src.children.some((c) => c.kind === 'dir' && c.name === 'components'), 'nested components')
assert(src.children.some((c) => c.kind === 'file' && c.name === 'App.tsx'), 'App under src')

const dirs = dirsContainingPaths(['src/components/dashboard/MetricCard.tsx'])
assert(dirs.has('src'), 'src ancestor')
assert(dirs.has('src/components'), 'components ancestor')
assert(dirs.has('src/components/dashboard'), 'dashboard ancestor')
assert(basename('a/b/c.ts') === 'c.ts', 'basename')

console.log('fileTree.selftest: ok')
