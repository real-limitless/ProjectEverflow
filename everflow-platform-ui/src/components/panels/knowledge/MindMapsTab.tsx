import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, FormGroup, TextInput, ToggleGroup, ToggleGroupItem } from '@patternfly/react-core'
import PencilAltIcon from '@patternfly/react-icons/dist/esm/icons/pencil-alt-icon'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { pushToast } from '@/lib/studioToast'
import { useStudioDemoStore } from '@/store/studioDemoStore'
import type { MindMap } from '@/types/studio'
import { MermaidView } from './MermaidView'

type ViewMode = 'edit' | 'preview'

interface MindMapsTabProps {
  projectId: string
  mindMaps: MindMap[]
}

export function MindMapsTab({ projectId, mindMaps }: MindMapsTabProps) {
  const createMindMap = useStudioDemoStore((s) => s.createMindMap)
  const updateMindMap = useStudioDemoStore((s) => s.updateMindMap)
  const deleteMindMap = useStudioDemoStore((s) => s.deleteMindMap)

  const [activeId, setActiveId] = useState(mindMaps[0]?.id ?? '')
  const [mapOpen, setMapOpen] = useState(false)
  const [mapName, setMapName] = useState('')
  const [useStarter, setUseStarter] = useState(false)
  const [mode, setMode] = useState<ViewMode>('edit')
  const [draftName, setDraftName] = useState('')
  const [draftMermaid, setDraftMermaid] = useState('')
  const [baselineName, setBaselineName] = useState('')
  const [baselineMermaid, setBaselineMermaid] = useState('')
  const [saveState, setSaveState] = useState<'idle' | 'saved'>('idle')
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const savedTimer = useRef<number | null>(null)
  const skipRenameBlur = useRef(false)
  const draftRef = useRef({ name: '', mermaid: '', baselineName: '', baselineMermaid: '' })

  const mind = mindMaps.find((m) => m.id === activeId) ?? mindMaps[0] ?? null

  const dirty =
    !!mind &&
    (draftMermaid !== baselineMermaid || draftName.trim() !== baselineName)

  draftRef.current = {
    name: draftName,
    mermaid: draftMermaid,
    baselineName,
    baselineMermaid,
  }

  const loadMap = useCallback((m: MindMap | null) => {
    if (!m) {
      setDraftName('')
      setDraftMermaid('')
      setBaselineName('')
      setBaselineMermaid('')
      setRenaming(false)
      return
    }
    const src = m.mermaid || ''
    setDraftName(m.name)
    setDraftMermaid(src)
    setBaselineName(m.name)
    setBaselineMermaid(src)
    setSaveState('idle')
    setRenaming(false)
    setMode(src.trim() ? 'preview' : 'edit')
  }, [])

  const saveMap = useCallback(
    (target?: MindMap | null, opts?: { silent?: boolean }) => {
      const m = target ?? mind
      if (!m) return false

      const isActive = !target || target.id === mind?.id
      const name = (isActive ? draftName : draftRef.current.name).trim() || m.name
      const mermaid = isActive ? draftMermaid : draftRef.current.mermaid
      const baseName = isActive ? baselineName : draftRef.current.baselineName
      const baseMermaid = isActive ? baselineMermaid : draftRef.current.baselineMermaid

      const nameDirty = name !== baseName
      const bodyDirty = mermaid !== baseMermaid
      if (!nameDirty && !bodyDirty) return false

      updateMindMap(projectId, m.id, { name, mermaid })

      if (isActive) {
        setDraftName(name)
        setDraftMermaid(mermaid)
        setBaselineName(name)
        setBaselineMermaid(mermaid)
      }

      if (!opts?.silent) {
        setSaveState('saved')
        if (savedTimer.current) window.clearTimeout(savedTimer.current)
        savedTimer.current = window.setTimeout(() => setSaveState('idle'), 2000)
        pushToast('Mind map saved', { kind: 'success' })
      }
      return true
    },
    [baselineMermaid, baselineName, draftMermaid, draftName, mind, projectId, updateMindMap],
  )

  useEffect(() => {
    if (!mindMaps.length) {
      setActiveId('')
      return
    }
    if (!activeId || !mindMaps.some((m) => m.id === activeId)) {
      setActiveId(mindMaps[0].id)
    }
  }, [mindMaps, activeId])

  useEffect(() => {
    loadMap(mind)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- switch by id only
  }, [mind?.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (dirty) saveMap()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dirty, saveMap])

  useEffect(
    () => () => {
      if (savedTimer.current) window.clearTimeout(savedTimer.current)
    },
    [],
  )

  useEffect(() => {
    if (!renaming) return
    window.requestAnimationFrame(() => {
      const el = document.getElementById('mm-rename-input') as HTMLInputElement | null
      el?.focus()
      el?.select()
    })
  }, [renaming])

  const selectMap = (id: string) => {
    if (id === activeId) return
    if (dirty && mind) saveMap(mind, { silent: true })
    setRenaming(false)
    setActiveId(id)
  }

  const startRename = () => {
    setRenameDraft(draftName)
    setRenaming(true)
  }

  const cancelRename = () => {
    skipRenameBlur.current = true
    setRenameDraft(draftName)
    setRenaming(false)
  }

  const commitRename = () => {
    if (!mind) {
      setRenaming(false)
      return
    }
    const name = renameDraft.trim() || mind.name
    setRenaming(false)
    if (name === mind.name && name === baselineName) {
      setDraftName(name)
      return
    }
    setDraftName(name)
    updateMindMap(projectId, mind.id, { name })
    setBaselineName(name)
    pushToast('Title updated', { kind: 'success' })
  }

  const createModal = (
    <CreateResourceModal
      isOpen={mapOpen}
      title="Create mind map"
      onClose={() => {
        setMapOpen(false)
        setUseStarter(false)
      }}
      onSubmit={() => {
        if (!mapName.trim()) return
        if (dirty && mind) saveMap(mind, { silent: true })
        const safe = mapName.trim().replace(/[()]/g, '')
        const starter = useStarter
          ? `mindmap\n  root((${safe}))\n    Branch A\n    Branch B`
          : ''
        const id = createMindMap(projectId, mapName.trim(), starter)
        setMapName('')
        setUseStarter(false)
        setMapOpen(false)
        setActiveId(id)
        setMode(starter ? 'preview' : 'edit')
        pushToast('Mind map created', {
          description: starter ? 'Starter outline applied' : 'Blank diagram — add Mermaid in Edit',
          kind: 'success',
        })
      }}
      isSubmitDisabled={!mapName.trim()}
    >
      <FormGroup label="Name" isRequired fieldId="mm-name">
        <TextInput id="mm-name" value={mapName} onChange={(_e, v) => setMapName(v)} />
      </FormGroup>
      <FormGroup label="Starting point" fieldId="mm-starter" style={{ marginTop: 12 }}>
        <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input
            id="mm-starter"
            type="checkbox"
            checked={useStarter}
            onChange={(e) => setUseStarter(e.target.checked)}
          />
          <span className="lc-meta">
            Include a simple starter outline (optional). Leave unchecked for a blank map you fill
            in yourself.
          </span>
        </label>
      </FormGroup>
    </CreateResourceModal>
  )

  if (mindMaps.length === 0) {
    return (
      <div className="canvas-empty">
        <EmptySplash
          title="No mind maps"
          body="Create a Mermaid diagram to map concepts, flows, or architecture for this project."
          primaryLabel="New mind map"
          onPrimary={() => setMapOpen(true)}
        />
        {createModal}
      </div>
    )
  }

  return (
    <div className="canvas-shell mm-shell">
      <aside className="canvas-sidebar">
        <div className="canvas-sidebar-toolbar">
          <Button size="sm" variant="primary" onClick={() => setMapOpen(true)}>
            New
          </Button>
        </div>
        <div className="canvas-sidebar-list" role="listbox" aria-label="Mind maps">
          {mindMaps.map((m) => {
            const active = m.id === mind?.id
            return (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={active}
                className={`canvas-nav-item${active ? ' is-active' : ''}`}
                onClick={() => selectMap(m.id)}
              >
                <span className="canvas-nav-title">{m.name}</span>
                <span className="canvas-nav-meta">
                  Mermaid
                  {m.updatedAt ? ` · ${m.updatedAt}` : ''}
                  {active && dirty ? ' · Unsaved' : ''}
                </span>
              </button>
            )
          })}
        </div>
      </aside>

      <section className="canvas-doc">
        {!mind ? (
          <div className="canvas-doc-fallback">
            <p>Select a mind map from the list.</p>
          </div>
        ) : (
          <>
            <header className="canvas-doc-header">
              <div className="canvas-doc-title-row">
                {renaming ? (
                  <div className="canvas-rename-row">
                    <TextInput
                      id="mm-rename-input"
                      value={renameDraft}
                      onChange={(_e, v) => setRenameDraft(v)}
                      aria-label="Rename mind map"
                      className="canvas-doc-title"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          skipRenameBlur.current = true
                          commitRename()
                        } else if (e.key === 'Escape') {
                          e.preventDefault()
                          cancelRename()
                        }
                      }}
                      onBlur={() => {
                        if (skipRenameBlur.current) {
                          skipRenameBlur.current = false
                          return
                        }
                        commitRename()
                      }}
                    />
                    <Button
                      size="sm"
                      variant="primary"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        skipRenameBlur.current = true
                      }}
                      onClick={() => commitRename()}
                    >
                      Done
                    </Button>
                    <Button
                      size="sm"
                      variant="link"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        skipRenameBlur.current = true
                      }}
                      onClick={() => cancelRename()}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <div className="canvas-title-display">
                    <h2 className="canvas-doc-heading" title={draftName}>
                      {draftName || 'Untitled'}
                    </h2>
                    <Button
                      variant="plain"
                      size="sm"
                      aria-label="Rename mind map"
                      className="canvas-rename-btn"
                      onClick={startRename}
                      icon={<PencilAltIcon />}
                    >
                      Rename
                    </Button>
                  </div>
                )}
                <span
                  className={`canvas-save-status${dirty ? ' is-dirty' : ''}${saveState === 'saved' ? ' is-saved' : ''}`}
                  aria-live="polite"
                >
                  {dirty ? 'Unsaved changes' : saveState === 'saved' ? 'Saved' : 'Up to date'}
                </span>
              </div>

              <div className="canvas-doc-actions">
                <ToggleGroup className="canvas-mode-toggle" aria-label="Editor mode">
                  <ToggleGroupItem
                    text="Edit"
                    buttonId="mm-mode-edit"
                    isSelected={mode === 'edit'}
                    onChange={() => setMode('edit')}
                  />
                  <ToggleGroupItem
                    text="Preview"
                    buttonId="mm-mode-preview"
                    isSelected={mode === 'preview'}
                    onChange={() => setMode('preview')}
                  />
                </ToggleGroup>
                <div className="canvas-doc-action-group">
                  <Button
                    size="sm"
                    variant="primary"
                    isDisabled={!dirty}
                    onClick={() => saveMap()}
                    title="Save diagram (Ctrl/⌘+S)"
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      const id = mind.id
                      deleteMindMap(projectId, id)
                      const remaining = mindMaps.filter((m) => m.id !== id)
                      setActiveId(remaining[0]?.id ?? '')
                      pushToast('Mind map deleted', { kind: 'info' })
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>

              <div className="canvas-doc-sub">
                <span className="canvas-chip canvas-chip--kind">Mermaid</span>
              </div>
            </header>

            <div className="canvas-doc-body mm-doc-body">
              {mode === 'edit' ? (
                <textarea
                  className="canvas-md-source"
                  value={draftMermaid}
                  onChange={(e) => {
                    setDraftMermaid(e.target.value)
                    setSaveState('idle')
                  }}
                  aria-label="Mermaid source"
                  spellCheck={false}
                  placeholder={`mindmap\n  root((Topic))\n    Branch A\n    Branch B`}
                />
              ) : (
                <div className="mm-diagram-pane">
                  {draftMermaid.trim() ? (
                    <MermaidView source={draftMermaid} />
                  ) : (
                    <div className="reader-mode-iframe-fallback" style={{ margin: 16 }}>
                      <p>This mind map is empty.</p>
                      <p className="lc-meta">
                        Switch to Edit and add Mermaid, for example:
                      </p>
                      <pre className="lc-meta" style={{ whiteSpace: 'pre-wrap' }}>
                        {`mindmap\n  root((${(draftName || 'Topic').replace(/[()]/g, '')}))\n    Idea A\n    Idea B`}
                      </pre>
                      <Button size="sm" variant="primary" onClick={() => setMode('edit')}>
                        Edit diagram
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </section>

      {createModal}
    </div>
  )
}
