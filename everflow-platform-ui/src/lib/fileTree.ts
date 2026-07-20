import type { ProjectFile } from '@/types/project'

export type FileTreeNode =
  | {
      kind: 'dir'
      name: string
      path: string
      children: FileTreeNode[]
    }
  | {
      kind: 'file'
      name: string
      path: string
      file: ProjectFile
    }

/** Build a nested folder tree from flat project file paths. */
export function buildFileTree(files: ProjectFile[]): FileTreeNode[] {
  type MutableDir = {
    kind: 'dir'
    name: string
    path: string
    children: Map<string, MutableDir | FileTreeNode>
  }

  const root: MutableDir = {
    kind: 'dir',
    name: '',
    path: '',
    children: new Map(),
  }

  for (const file of files) {
    const parts = file.path.split('/').filter(Boolean)
    if (parts.length === 0) continue
    let node = root
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i]
      const dirPath = parts.slice(0, i + 1).join('/')
      let child = node.children.get(part)
      if (!child || child.kind !== 'dir') {
        child = {
          kind: 'dir',
          name: part,
          path: dirPath,
          children: new Map(),
        }
        node.children.set(part, child)
      }
      node = child as MutableDir
    }
    const name = parts[parts.length - 1]
    node.children.set(name, {
      kind: 'file',
      name,
      path: file.path,
      file,
    })
  }

  const finalize = (dir: MutableDir): FileTreeNode[] => {
    const entries = [...dir.children.values()]
    entries.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    return entries.map((entry) => {
      if (entry.kind === 'dir') {
        const m = entry as MutableDir
        return {
          kind: 'dir' as const,
          name: m.name,
          path: m.path,
          children: finalize(m),
        }
      }
      return entry
    })
  }

  return finalize(root)
}

/** Collect dir paths that contain any of the given file paths as descendants. */
export function dirsContainingPaths(filePaths: Iterable<string>): Set<string> {
  const dirs = new Set<string>()
  for (const path of filePaths) {
    const parts = path.split('/').filter(Boolean)
    for (let i = 1; i < parts.length; i++) {
      dirs.add(parts.slice(0, i).join('/'))
    }
  }
  return dirs
}

export function basename(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts[parts.length - 1] || path
}
