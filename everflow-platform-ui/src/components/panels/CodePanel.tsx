import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  MenuToggle,
  Spinner,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import AngleDownIcon from '@patternfly/react-icons/dist/esm/icons/angle-down-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'
import { getProject, updateProjectInCatalog } from '@/data/projects'
import {
  ApiError,
  listSandboxFs,
  readSandboxFs,
  writeSandboxFs,
} from '@/lib/api'
import { basename, buildFileTree, type FileTreeNode } from '@/lib/fileTree'
import { highlightCode, lintCode } from '@/lib/syntaxHighlight'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type { PanelKey } from '@/types/panels'
import type { GitFileChange, ProjectFile } from '@/types/project'

interface CodePanelProps {
  panelKey: PanelKey
}

function resolveSource(
  code: Record<string, string> | undefined,
  path: string,
  name: string,
): string {
  if (!code) return ''
  return code[path] || code[name] || code[basename(path)] || ''
}

function GitStats({ change }: { change?: GitFileChange }) {
  if (!change) return null
  const statusClass =
    change.status === 'A'
      ? 'badge-a'
      : change.status === 'D'
        ? 'badge-d'
        : change.status === 'M'
          ? 'badge-m'
          : 'badge-u'
  return (
    <span className="tree-git" title={`${change.status} +${change.additions} −${change.deletions}`}>
      <span className={statusClass}>{change.status}</span>
      {(change.additions > 0 || change.deletions > 0) && (
        <span className="tree-diff-stats">
          {change.additions > 0 && <span className="diff-add-n">+{change.additions}</span>}
          {change.deletions > 0 && <span className="diff-del-n">−{change.deletions}</span>}
        </span>
      )}
    </span>
  )
}

function TreeRows({
  nodes,
  depth,
  activePath,
  expanded,
  changesByPath,
  onToggle,
  onOpen,
}: {
  nodes: FileTreeNode[]
  depth: number
  activePath: string
  expanded: Set<string>
  changesByPath: Map<string, GitFileChange>
  onToggle: (path: string) => void
  onOpen: (path: string) => void
}) {
  return (
    <>
      {nodes.map((node) => {
        if (node.kind === 'dir') {
          const isOpen = expanded.has(node.path)
          const hasChange = [...changesByPath.keys()].some(
            (p) => p === node.path || p.startsWith(`${node.path}/`),
          )
          return (
            <div key={`d:${node.path}`}>
              <button
                type="button"
                className={`tree-item folder${hasChange ? ' has-change' : ''}`}
                style={{ paddingInlineStart: `${0.35 + depth * 0.75}rem` }}
                onClick={() => onToggle(node.path)}
                aria-expanded={isOpen}
              >
                {isOpen ? <AngleDownIcon /> : <AngleRightIcon />}
                <span className="tree-name">{node.name}</span>
              </button>
              {isOpen ? (
                <TreeRows
                  nodes={node.children || []}
                  depth={depth + 1}
                  activePath={activePath}
                  expanded={expanded}
                  changesByPath={changesByPath}
                  onToggle={onToggle}
                  onOpen={onOpen}
                />
              ) : null}
            </div>
          )
        }

        const change = changesByPath.get(node.path)
        const isActive = node.path === activePath || node.name === activePath
        return (
          <button
            key={`f:${node.path}`}
            type="button"
            className={`tree-item file${isActive ? ' active' : ''}${change ? ` git-${change.status.toLowerCase()}` : ''}`}
            style={{ paddingInlineStart: `${0.35 + depth * 0.75 + 0.85}rem` }}
            onClick={() => onOpen(node.path)}
            title={node.path}
          >
            <span className="tree-name">{node.name}</span>
            <GitStats change={change} />
          </button>
        )
      })}
    </>
  )
}

const FS_MAX_DEPTH = 12
const FS_MAX_FILES = 4000

/**
 * Heavy / VCS / build artifacts skipped during recursive tree walk so real source
 * stays under the file cap. Names match a single path segment.
 */
const FS_SKIP_DIR_NAMES = new Set([
  'node_modules',
  '.git',
  '.svn',
  '.hg',
  '.everflow',
  '__pycache__',
  '.venv',
  'venv',
  '.tox',
  'dist',
  'build',
  'out',
  '.next',
  '.nuxt',
  '.turbo',
  '.cache',
  'coverage',
  'target',
  'vendor',
  '.yarn',
  '.pnpm-store',
  'Pods',
  '.idea',
  '.gradle',
  'bower_components',
])

function shouldSkipFsDir(name: string): boolean {
  if (!name || name === '.' || name === '..') return true
  if (FS_SKIP_DIR_NAMES.has(name)) return true
  // e.g. .gitkeep stays; skip other dotted cache dirs that are usually huge
  if (name.startsWith('.') && (name.endsWith('_cache') || name.endsWith('-cache'))) return true
  return false
}

/** Normalize a workspace-relative path from the sandbox agent (no leading ./). */
function cleanFsPath(path: string, dir: string, name: string): string {
  let raw = (path || '').replace(/^\.\//, '').replace(/\/+$/, '')
  if (!raw || raw === '.') {
    raw = dir && dir !== '.' ? `${dir.replace(/^\.\//, '')}/${name}` : name
  }
  return raw.replace(/^\.\//, '').replace(/\/+/g, '/')
}

/**
 * Recursively list sandbox workspace files under `dir`.
 * Skips heavy dirs (node_modules, .git, …), guards cycles, and caps depth/size.
 */
async function collectRemoteTree(
  projectId: string,
  dir = '.',
  acc: ProjectFile[] = [],
  visited: Set<string> = new Set(),
  depth = 0,
): Promise<{ files: ProjectFile[]; truncated: boolean }> {
  if (depth > FS_MAX_DEPTH || acc.length >= FS_MAX_FILES) {
    return { files: acc, truncated: true }
  }
  const listKey = dir || '.'
  if (visited.has(listKey)) {
    return { files: acc, truncated: false }
  }
  visited.add(listKey)

  const entries = await listSandboxFs(projectId, listKey)
  let truncated = false
  for (const e of entries) {
    if (acc.length >= FS_MAX_FILES) {
      truncated = true
      break
    }
    if (!e.name || e.name === '.' || e.name === '..') {
      continue
    }
    if (e.is_dir && shouldSkipFsDir(e.name)) {
      continue
    }
    const clean = cleanFsPath(e.path, listKey, e.name)
    if (!clean || clean === '.' || clean === '..' || visited.has(`f:${clean}`)) {
      continue
    }
    if (e.is_dir) {
      const nested = await collectRemoteTree(projectId, clean, acc, visited, depth + 1)
      if (nested.truncated) truncated = true
    } else {
      visited.add(`f:${clean}`)
      acc.push({
        path: clean,
        name: e.name,
        folder: clean.includes('/') ? clean.slice(0, clean.lastIndexOf('/')) : '',
      })
    }
  }
  return { files: acc, truncated }
}

export function CodePanel({ panelKey }: CodePanelProps) {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const st = usePlaygroundStore((s) => s.instanceState[panelKey])
  const openCodeFile = usePlaygroundStore((s) => s.openCodeFile)
  const closeCodeFile = usePlaygroundStore((s) => s.closeCodeFile)
  const setCodeFontSize = usePlaygroundStore((s) => s.setCodeFontSize)
  const toggleCodeFolder = usePlaygroundStore((s) => s.toggleCodeFolder)

  const p = getProject(currentProjectId)
  void catalogVersion
  const files = p?.files
  const changes = p?.gitChanges
  const fromApi = Boolean(p?.fromApi)
  const sandboxRunning = p?.sandboxStatus === 'running'

  const [loadingFs, setLoadingFs] = useState(false)
  const [fsError, setFsError] = useState<string | null>(null)
  const [fsLoaded, setFsLoaded] = useState(false)
  const [fsTruncated, setFsTruncated] = useState(false)
  const [draft, setDraft] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editMode, setEditMode] = useState(fromApi)
  const editGutterRef = useRef<HTMLDivElement>(null)

  const refreshTree = useCallback(async () => {
    if (!fromApi || !currentProjectId || !sandboxRunning) return
    setLoadingFs(true)
    setFsError(null)
    try {
      const { files: treeFiles, truncated } = await collectRemoteTree(currentProjectId, '.')
      setFsTruncated(truncated)
      const existingCode = getProject(currentProjectId)?.code || {}
      const code: Record<string, string> = { ...existingCode }
      // Prefetch a small set of shallow files; open still loads on demand
      const shallow = treeFiles.filter((f) => !f.path.includes('/')).slice(0, 8)
      for (const f of shallow) {
        if (code[f.path] || code[f.name]) continue
        try {
          code[f.path] = await readSandboxFs(currentProjectId, f.path)
        } catch {
          /* skip unreadable / binary */
        }
      }
      // Prefer live sandbox listing over catalog seed once remote list succeeds
      updateProjectInCatalog(currentProjectId, { files: treeFiles, code })
      usePlaygroundStore.setState({
        catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
      })
      setFsLoaded(true)
      if (truncated) {
        pushToast(
          'Workspace tree truncated (file/depth limit). node_modules and .git are already skipped.',
          { kind: 'info' },
        )
      }
    } catch (e) {
      setFsError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'FS error')
      setFsLoaded(false)
    } finally {
      setLoadingFs(false)
    }
    // Intentionally omit catalog `code` / `files` — updating them must not re-trigger refresh
  }, [currentProjectId, fromApi, sandboxRunning])

  useEffect(() => {
    if (!fromApi || !sandboxRunning) {
      setFsLoaded(false)
      setFsTruncated(false)
      return
    }
    void refreshTree()
  }, [fromApi, sandboxRunning, currentProjectId, refreshTree])

  const changesByPath = useMemo(() => {
    const map = new Map<string, GitFileChange>()
    for (const c of changes || []) map.set(c.path, c)
    return map
  }, [changes])

  const treeFiles: ProjectFile[] = useMemo(() => {
    const byPath = new Map((files || []).map((f) => [f.path, f]))
    for (const c of changes || []) {
      if (c.status === 'D' && !byPath.has(c.path)) {
        byPath.set(c.path, {
          path: c.path,
          name: c.label || basename(c.path),
          folder: c.path.includes('/')
            ? c.path.slice(0, c.path.lastIndexOf('/'))
            : '',
        })
      }
    }
    return [...byPath.values()]
  }, [files, changes])

  const tree = useMemo(() => buildFileTree(treeFiles), [treeFiles])

  const activePath =
    st?.file ||
    st?.openFiles?.[0] ||
    files?.[0]?.path ||
    files?.[0]?.name ||
    ''

  const openFiles = useMemo(() => {
    const list = st?.openFiles?.length
      ? st.openFiles
      : activePath
        ? [activePath]
        : []
    return list
  }, [st?.openFiles, activePath])

  const expanded = useMemo(
    () => new Set(st?.expandedFolders || []),
    [st?.expandedFolders],
  )

  const fontSize = st?.codeFontSize ?? 12

  const activeFileMeta =
    treeFiles.find((f) => f.path === activePath || f.name === activePath) ||
    files?.find((f) => f.path === activePath || f.name === activePath)

  const activeName = activeFileMeta?.name || basename(activePath)
  const rawSource = resolveSource(p?.code, activePath, activeName)

  // Load file content from sandbox when opening
  useEffect(() => {
    if (!fromApi || !currentProjectId || !activePath || !sandboxRunning) {
      setDraft(rawSource)
      setDirty(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const text = await readSandboxFs(currentProjectId, activePath)
        if (cancelled) return
        setDraft(text)
        setDirty(false)
        updateProjectInCatalog(currentProjectId, {
          code: { ...(getProject(currentProjectId)?.code || {}), [activePath]: text },
        })
        usePlaygroundStore.setState({
          catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
        })
      } catch {
        if (!cancelled) {
          setDraft(rawSource)
          setDirty(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activePath, currentProjectId, fromApi, sandboxRunning]) // eslint-disable-line react-hooks/exhaustive-deps

  const displaySource = fromApi && editMode ? draft : rawSource || draft
  const highlighted = useMemo(
    () => highlightCode(displaySource, activeName),
    [displaySource, activeName],
  )
  const diagnostics = useMemo(
    () => lintCode(displaySource, activeName),
    [displaySource, activeName],
  )
  const diagByLine = useMemo(() => {
    const m = new Map<number, (typeof diagnostics)[0]>()
    for (const d of diagnostics) m.set(d.line, d)
    return m
  }, [diagnostics])

  const lines = highlighted ? highlighted.split('\n') : []
  const [showLint, setShowLint] = useState(true)
  const [editorMenuOpen, setEditorMenuOpen] = useState(false)

  const save = async () => {
    if (!currentProjectId || !activePath || !fromApi) return
    setSaving(true)
    try {
      await writeSandboxFs(currentProjectId, activePath, draft)
      updateProjectInCatalog(currentProjectId, {
        code: { ...(getProject(currentProjectId)?.code || {}), [activePath]: draft },
      })
      usePlaygroundStore.setState({
        catalogVersion: usePlaygroundStore.getState().catalogVersion + 1,
      })
      setDirty(false)
      pushToast(`Saved ${activeName}`, { kind: 'success' })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Save failed', { kind: 'danger' })
    } finally {
      setSaving(false)
    }
  }

  if (!p) {
    return (
      <div className="code-layout code-empty">
        <div className="code-empty-msg">Open a project to browse source files.</div>
      </div>
    )
  }

  return (
    <div className="code-layout">
      <div className="file-tree">
        <div className="tree-label">
          Explorer
          {fromApi ? (
            <Button
              variant="link"
              isInline
              size="sm"
              onClick={() => void refreshTree()}
              isDisabled={loadingFs || !sandboxRunning}
            >
              {loadingFs ? <Spinner size="sm" /> : 'Refresh'}
            </Button>
          ) : null}
        </div>
        {fsError ? <div className="code-fs-error">{fsError}</div> : null}
        {fsTruncated ? (
          <div className="code-fs-error">
            Tree truncated (file or depth limit). Heavy folders like node_modules and .git are skipped
            automatically — click Refresh after reducing large source trees.
          </div>
        ) : null}
        {fromApi && !sandboxRunning ? (
          <div className="code-empty-msg">Sandbox {p.sandboxStatus || 'pending'}…</div>
        ) : fromApi && loadingFs && !fsLoaded && tree.length === 0 ? (
          <div className="code-empty-msg">
            <Spinner size="sm" /> Loading workspace…
          </div>
        ) : fromApi && fsLoaded && tree.length === 0 && !fsError ? (
          <div className="code-empty-msg">Workspace is empty</div>
        ) : (
          <TreeRows
            nodes={tree}
            depth={0}
            activePath={activePath}
            expanded={expanded}
            changesByPath={changesByPath}
            onToggle={(path) => toggleCodeFolder(panelKey, path)}
            onOpen={(path) => openCodeFile(panelKey, path)}
          />
        )}
        {(changes?.length ?? 0) > 0 && (
          <div className="tree-legend" title="From Repository → Changes">
            <span className="badge-m">M</span> modified
            <span className="badge-a">A</span> added
            <span className="badge-d">D</span> deleted
          </div>
        )}
      </div>

      <div className="editor">
        <div className="editor-toolbar">
          <div className="editor-tabs" role="tablist">
            {openFiles.map((path) => {
              const name =
                treeFiles.find((f) => f.path === path)?.name || basename(path)
              const change = changesByPath.get(path)
              const active = path === activePath
              return (
                <div
                  key={path}
                  className={`editor-tab${active ? ' active' : ''}`}
                  role="tab"
                  aria-selected={active}
                >
                  <button
                    type="button"
                    className="editor-tab-label"
                    onClick={() => openCodeFile(panelKey, path)}
                    title={path}
                  >
                    {change && (
                      <span className={`tab-git badge-${change.status.toLowerCase()}`}>
                        {change.status}
                      </span>
                    )}
                    <span>
                      {name}
                      {active && dirty ? ' •' : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="editor-tab-close"
                    aria-label={`Close ${name}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      closeCodeFile(panelKey, path)
                    }}
                  >
                    <TimesIcon />
                  </button>
                </div>
              )
            })}
          </div>
          <div className="editor-controls">
            {fromApi ? (
              <>
                <ToggleGroup className="editor-mode-toggle" aria-label="Editor mode">
                  <ToggleGroupItem
                    text="Edit"
                    buttonId="editor-mode-edit"
                    isSelected={editMode}
                    onChange={() => setEditMode(true)}
                    title="Edit file in sandbox"
                  />
                  <ToggleGroupItem
                    text="View"
                    buttonId="editor-mode-view"
                    isSelected={!editMode}
                    onChange={() => setEditMode(false)}
                    title="Read-only syntax-highlighted view"
                  />
                </ToggleGroup>
                <Button
                  variant="primary"
                  size="sm"
                  isDisabled={!dirty || !sandboxRunning}
                  isLoading={saving}
                  onClick={() => void save()}
                >
                  Save
                </Button>
              </>
            ) : null}
            <Dropdown
              isOpen={editorMenuOpen}
              onOpenChange={setEditorMenuOpen}
              onSelect={(_event, itemId) => {
                if (itemId === 'font-dec') {
                  if (fontSize > 10) setCodeFontSize(panelKey, fontSize - 1)
                  return
                }
                if (itemId === 'font-inc') {
                  if (fontSize < 22) setCodeFontSize(panelKey, fontSize + 1)
                  return
                }
                if (itemId === 'lint') {
                  setShowLint((v) => !v)
                }
                setEditorMenuOpen(false)
              }}
              popperProps={{ position: 'right' }}
              toggle={(toggleRef) => (
                <MenuToggle
                  ref={toggleRef}
                  className="editor-menu-toggle"
                  size="sm"
                  onClick={() => setEditorMenuOpen((open) => !open)}
                  isExpanded={editorMenuOpen}
                  aria-label="Editor settings"
                >
                  Editor
                </MenuToggle>
              )}
            >
              <DropdownList>
                <DropdownItem
                  value="lint"
                  description={
                    diagnostics.length > 0
                      ? `${diagnostics.length} problem${diagnostics.length === 1 ? '' : 's'}`
                      : undefined
                  }
                >
                  {showLint ? 'Hide lint markers' : 'Show lint markers'}
                </DropdownItem>
                <DropdownItem value="font-dec" isDisabled={fontSize <= 10}>
                  Decrease font size (A−)
                </DropdownItem>
                <DropdownItem value="font-inc" isDisabled={fontSize >= 22}>
                  Increase font size (A+) · {fontSize}px
                </DropdownItem>
              </DropdownList>
            </Dropdown>
          </div>
        </div>

        <div className="editor-body" style={{ fontSize: `${fontSize}px` }}>
          {!activePath ? (
            <div className="code-empty-msg">Select a file from the tree to open it.</div>
          ) : fromApi && editMode ? (
            <div className="code-edit-wrap" style={{ fontSize: `${fontSize}px` }}>
              <div
                ref={editGutterRef}
                className="code-edit-gutter"
                aria-hidden
              >
                {Array.from(
                  { length: Math.max(1, draft.split('\n').length) },
                  (_, i) => (
                    <div key={i + 1} className="code-edit-ln">
                      {i + 1}
                    </div>
                  ),
                )}
              </div>
              <textarea
                className="code-edit-area"
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value)
                  setDirty(true)
                }}
                onScroll={(e) => {
                  const gutter = editGutterRef.current
                  if (gutter) gutter.scrollTop = e.currentTarget.scrollTop
                }}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                    e.preventDefault()
                    void save()
                  }
                }}
                spellCheck={false}
                style={{ fontSize: `${fontSize}px` }}
                aria-label={`Edit ${activeName}`}
              />
            </div>
          ) : lines.length === 0 ? (
            <div className="code-empty-msg">
              {changesByPath.get(activePath)?.status === 'D'
                ? 'File deleted in working tree.'
                : 'No content for this file.'}
            </div>
          ) : (
            <table>
              <tbody>
                {lines.map((line, i) => {
                  const lineNo = i + 1
                  const diag = showLint ? diagByLine.get(lineNo) : undefined
                  return (
                    <tr
                      key={i}
                      className={diag ? `lint-line lint-${diag.severity}` : undefined}
                    >
                      <td className="lint-gutter" title={diag?.message}>
                        {diag && (
                          <span
                            className={`lint-mark lint-mark-${diag.severity}`}
                            aria-label={diag.message}
                          />
                        )}
                      </td>
                      <td className="ln">{lineNo}</td>
                      <td
                        className="code"
                        dangerouslySetInnerHTML={{ __html: line || ' ' }}
                      />
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {showLint && diagnostics.length > 0 && !(fromApi && editMode) && (
          <div className="lint-panel" role="status">
            <div className="lint-panel-title">Problems · {diagnostics.length}</div>
            <ul className="lint-list">
              {diagnostics.slice(0, 8).map((d) => (
                <li key={`${d.line}-${d.message}`} className={`lint-item severity-${d.severity}`}>
                  <span className="lint-sev">{d.severity}</span>
                  <span className="lint-msg">{d.message}</span>
                  <span className="lint-loc">
                    {activeName}:{d.line}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
