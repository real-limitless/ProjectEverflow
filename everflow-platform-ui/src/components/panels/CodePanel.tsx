import { useMemo, useState } from 'react'
import AngleDownIcon from '@patternfly/react-icons/dist/esm/icons/angle-down-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'
import { getProject } from '@/data/projects'
import { basename, buildFileTree, type FileTreeNode } from '@/lib/fileTree'
import { highlightCode, lintCode } from '@/lib/syntaxHighlight'
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
                <span className="tree-chevron" aria-hidden>
                  {isOpen ? <AngleDownIcon /> : <AngleRightIcon />}
                </span>
                <span className="tree-name">{node.name}</span>
              </button>
              {isOpen && (
                <TreeRows
                  nodes={node.children}
                  depth={depth + 1}
                  activePath={activePath}
                  expanded={expanded}
                  changesByPath={changesByPath}
                  onToggle={onToggle}
                  onOpen={onOpen}
                />
              )}
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

export function CodePanel({ panelKey }: CodePanelProps) {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const st = usePlaygroundStore((s) => s.instanceState[panelKey])
  const openCodeFile = usePlaygroundStore((s) => s.openCodeFile)
  const closeCodeFile = usePlaygroundStore((s) => s.closeCodeFile)
  const setCodeFontSize = usePlaygroundStore((s) => s.setCodeFontSize)
  const toggleCodeFolder = usePlaygroundStore((s) => s.toggleCodeFolder)

  const p = getProject(currentProjectId)
  const files = p?.files
  const changes = p?.gitChanges

  const changesByPath = useMemo(() => {
    const map = new Map<string, GitFileChange>()
    for (const c of changes || []) map.set(c.path, c)
    return map
  }, [changes])

  // Include deleted paths in the tree so they remain visible with a D badge
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
  const highlighted = useMemo(
    () => highlightCode(rawSource, activeName),
    [rawSource, activeName],
  )
  const diagnostics = useMemo(
    () => lintCode(rawSource, activeName),
    [rawSource, activeName],
  )
  const diagByLine = useMemo(() => {
    const m = new Map<number, (typeof diagnostics)[0]>()
    for (const d of diagnostics) m.set(d.line, d)
    return m
  }, [diagnostics])

  const lines = highlighted ? highlighted.split('\n') : []
  const [showLint, setShowLint] = useState(true)

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
        <div className="tree-label">Explorer</div>
        <TreeRows
          nodes={tree}
          depth={0}
          activePath={activePath}
          expanded={expanded}
          changesByPath={changesByPath}
          onToggle={(path) => toggleCodeFolder(panelKey, path)}
          onOpen={(path) => openCodeFile(panelKey, path)}
        />
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
                    <span>{name}</span>
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
            <button
              type="button"
              className={`editor-ctrl-btn${showLint ? ' active' : ''}`}
              title={showLint ? 'Hide lint markers' : 'Show lint markers'}
              onClick={() => setShowLint((v) => !v)}
            >
              Lint
              {diagnostics.length > 0 && (
                <span className="lint-count">{diagnostics.length}</span>
              )}
            </button>
            <div className="font-size-ctrl" title="Editor font size">
              <button
                type="button"
                className="editor-ctrl-btn"
                aria-label="Decrease font size"
                disabled={fontSize <= 10}
                onClick={() => setCodeFontSize(panelKey, fontSize - 1)}
              >
                A−
              </button>
              <span className="font-size-val">{fontSize}</span>
              <button
                type="button"
                className="editor-ctrl-btn"
                aria-label="Increase font size"
                disabled={fontSize >= 22}
                onClick={() => setCodeFontSize(panelKey, fontSize + 1)}
              >
                A+
              </button>
            </div>
          </div>
        </div>

        <div
          className="editor-body"
          style={{ fontSize: `${fontSize}px` }}
        >
          {!activePath ? (
            <div className="code-empty-msg">Select a file from the tree to open it.</div>
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

        {showLint && diagnostics.length > 0 && (
          <div className="lint-panel" role="status">
            <div className="lint-panel-title">
              Problems · {diagnostics.length}
            </div>
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
