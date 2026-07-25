import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button,
  Dropdown,
  DropdownItem,
  DropdownList,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  TextInput,
  ToggleGroup,
  ToggleGroupItem,
} from '@patternfly/react-core'
import TimesIcon from '@patternfly/react-icons/dist/esm/icons/times-icon'
import EllipsisVIcon from '@patternfly/react-icons/dist/esm/icons/ellipsis-v-icon'
import PencilAltIcon from '@patternfly/react-icons/dist/esm/icons/pencil-alt-icon'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  createKnowledgeCollection,
  deleteKnowledgeCollection,
  indexKnowledgeRepo,
  isDemoMode,
  listKnowledgeCanvasVersions,
  listKnowledgeCollections,
  refreshKnowledgeCanvasSource,
  reindexKnowledgeCanvas,
  upsertCollectionGrant,
  type ApiKnowledgeCollection,
  type ApiKnowledgeVersion,
  listProjectAgents,
} from '@/lib/api'
import { mapApiCanvas } from '@/lib/studioMap'
import { pushToast } from '@/lib/studioToast'
import { useStudioDemoStore } from '@/store/studioDemoStore'
import type { KnowledgeCanvas } from '@/types/studio'
import {
  chatKnowledgeLabel,
  isPipelineBusy,
  kindLabel,
  knowledgeActionLabel,
  sidebarMetaLine,
  statusToneColor,
} from './canvasStatus'
import { EmbedPipeline } from './EmbedPipeline'
import { MarkdownWorkbench, type MarkdownViewMode } from './MarkdownWorkbench'

function isLikelyPdf(files: FileList): boolean {
  return Array.from(files).some(
    (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'),
  )
}

interface CanvasTabProps {
  projectId: string
  canvases: KnowledgeCanvas[]
  onRefresh?: () => void
}

export function CanvasTab({ projectId, canvases, onRefresh }: CanvasTabProps) {
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const createCanvas = useStudioDemoStore((s) => s.createCanvas)
  const updateCanvas = useStudioDemoStore((s) => s.updateCanvas)
  const deleteCanvas = useStudioDemoStore((s) => s.deleteCanvas)
  const uploadToCanvas = useStudioDemoStore((s) => s.uploadToCanvas)
  const replaceCanvases = useStudioDemoStore((s) => s.update)

  const [activeId, setActiveId] = useState(canvases[0]?.id ?? '')
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftMd, setDraftMd] = useState('')
  const [baselineName, setBaselineName] = useState('')
  const [baselineMd, setBaselineMd] = useState('')
  const [mode, setMode] = useState<MarkdownViewMode>('edit')
  const [saveState, setSaveState] = useState<'idle' | 'saved'>('idle')
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const [overflowOpen, setOverflowOpen] = useState(false)
  const [diffOpen, setDiffOpen] = useState(false)
  const [versions, setVersions] = useState<ApiKnowledgeVersion[]>([])
  const [indexingRepo, setIndexingRepo] = useState(false)
  const [collections, setCollections] = useState<ApiKnowledgeCollection[]>([])
  const [collectionOpen, setCollectionOpen] = useState(false)
  const [collectionName, setCollectionName] = useState('')
  const [collectionVisibility, setCollectionVisibility] = useState<'team' | 'personal' | 'agent'>(
    'team',
  )
  const [collectionSaving, setCollectionSaving] = useState(false)
  /** null = all canvases; string id filters sidebar list */
  const [filterCollectionId, setFilterCollectionId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const savedTimer = useRef<number | null>(null)
  const draftRef = useRef({ name: '', md: '', baselineName: '', baselineMd: '' })
  const skipRenameBlur = useRef(false)

  const collectionById = useCallback(
    (id: string | undefined | null) =>
      id ? collections.find((c) => c.id === id) : undefined,
    [collections],
  )

  const visibleCanvases =
    filterCollectionId == null
      ? canvases
      : filterCollectionId === '__none__'
        ? canvases.filter((c) => !c.collectionId)
        : canvases.filter((c) => c.collectionId === filterCollectionId)

  const canvas =
    visibleCanvases.find((c) => c.id === activeId) ??
    canvases.find((c) => c.id === activeId) ??
    visibleCanvases[0] ??
    canvases[0] ??
    null

  const bodyDirty = !!canvas && draftMd !== baselineMd
  const nameDirty = !!canvas && draftName.trim() !== baselineName
  const dirty = bodyDirty || nameDirty

  const assignCollection = (collectionId: string | null) => {
    if (!canvas) return
    const next = collectionId || undefined
    if ((canvas.collectionId || undefined) === next) return
    updateCanvas(projectId, canvas.id, { collectionId: next })
    const col = collectionById(collectionId)
    pushToast(col ? `Assigned to “${col.name}”` : 'Removed from collection', {
      kind: 'success',
    })
  }

  draftRef.current = {
    name: draftName,
    md: draftMd,
    baselineName,
    baselineMd,
  }

  const loadCanvas = useCallback((c: KnowledgeCanvas | null) => {
    if (!c) {
      setDraftName('')
      setDraftMd('')
      setBaselineName('')
      setBaselineMd('')
      setRenaming(false)
      return
    }
    const body = c.contentMd ?? ''
    setDraftName(c.name)
    setDraftMd(body)
    setBaselineName(c.name)
    setBaselineMd(body)
    setSaveState('idle')
    setRenaming(false)
  }, [])

  const saveCanvas = useCallback(
    (target?: KnowledgeCanvas | null, opts?: { silent?: boolean }) => {
      const c = target ?? canvas
      if (!c) return false

      const isActive = !target || target.id === canvas?.id
      const name = (isActive ? draftName : draftRef.current.name).trim() || c.name
      const contentMd = isActive ? draftMd : draftRef.current.md
      const baseName = isActive ? baselineName : draftRef.current.baselineName
      const baseMd = isActive ? baselineMd : draftRef.current.baselineMd

      const nDirty = name !== baseName
      const bDirty = contentMd !== baseMd
      if (!nDirty && !bDirty) return false

      let nextStatus = c.status
      if (bDirty && (c.status === 'indexed' || c.status === 'stale')) {
        nextStatus = 'stale'
      }

      updateCanvas(projectId, c.id, {
        name,
        contentMd,
        status: nextStatus,
      })

      if (isActive) {
        setDraftName(name)
        setDraftMd(contentMd)
        setBaselineName(name)
        setBaselineMd(contentMd)
      }

      if (!opts?.silent) {
        setSaveState('saved')
        if (savedTimer.current) window.clearTimeout(savedTimer.current)
        savedTimer.current = window.setTimeout(() => setSaveState('idle'), 2000)
        pushToast('Canvas saved', { kind: 'success' })
      }
      return true
    },
    [baselineMd, baselineName, canvas, draftMd, draftName, projectId, updateCanvas],
  )

  useEffect(() => {
    if (!canvases.length) {
      setActiveId('')
      return
    }
    if (!activeId || !canvases.some((c) => c.id === activeId)) {
      setActiveId(canvases[0].id)
    }
  }, [canvases, activeId])

  useEffect(() => {
    loadCanvas(canvas)
    setMode('edit')
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on id switch
  }, [canvas?.id])

  useEffect(() => {
    if (!canvas) return
    if (!isPipelineBusy(canvas.status)) return
    if (dirty) return
    const body = canvas.contentMd ?? ''
    setDraftMd(body)
    setBaselineMd(body)
  }, [canvas, canvas?.status, canvas?.contentMd, dirty])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (dirty) saveCanvas()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dirty, saveCanvas])

  useEffect(
    () => () => {
      if (savedTimer.current) window.clearTimeout(savedTimer.current)
    },
    [],
  )

  useEffect(() => {
    if (!renaming) return
    window.requestAnimationFrame(() => {
      const el = document.getElementById('canvas-rename-input') as HTMLInputElement | null
      el?.focus()
      el?.select()
    })
  }, [renaming])

  const selectCanvas = (id: string) => {
    if (id === activeId) return
    if (dirty && canvas) {
      saveCanvas(canvas, { silent: true })
    }
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
    if (!canvas) {
      setRenaming(false)
      return
    }
    const name = renameDraft.trim() || canvas.name
    setRenaming(false)
    if (name === canvas.name && name === baselineName) {
      setDraftName(name)
      return
    }
    setDraftName(name)
    updateCanvas(projectId, canvas.id, { name })
    setBaselineName(name)
    pushToast('Title updated', { kind: 'success' })
  }

  const onUpload = (files: FileList | null) => {
    if (!files?.length) return
    if (dirty && canvas) saveCanvas(canvas, { silent: true })

    Array.from(files).forEach((f) => {
      const isText =
        f.type.startsWith('text/') || f.name.endsWith('.md') || f.name.endsWith('.txt')
      const sizeLabel =
        f.size > 1e6
          ? `${(f.size / 1e6).toFixed(1)} MB`
          : `${Math.max(1, Math.round(f.size / 1024))} KB`

      if (isText) {
        const reader = new FileReader()
        reader.onload = () => {
          const text = typeof reader.result === 'string' ? reader.result : undefined
          const id = uploadToCanvas(projectId, {
            name: f.name,
            mime: f.type || 'text/plain',
            sizeLabel,
            textContent: text,
          })
          setActiveId(id)
        }
        reader.readAsText(f)
      } else {
        const id = uploadToCanvas(projectId, {
          name: f.name,
          mime: f.type || 'application/octet-stream',
          sizeLabel,
        })
        setActiveId(id)
      }
    })
    pushToast('Upload started', {
      description: isLikelyPdf(files)
        ? 'Unlimited OCR converts the PDF to Markdown. Add to chatbot knowledge when ready.'
        : 'File imported as notes. Add to chatbot knowledge when you want retrieval.',
      kind: 'info',
    })
  }

  const reindex = async () => {
    if (!canvas || isPipelineBusy(canvas.status)) return
    if (dirty) saveCanvas(canvas, { silent: true })
    if (useApi) {
      try {
        updateCanvas(projectId, canvas.id, { status: 'chunking', chunks: 0 })
        const indexed = await reindexKnowledgeCanvas(projectId, canvas.id)
        replaceCanvases(projectId, (s) => ({
          ...s,
          canvases: s.canvases.map((c) =>
            c.id === canvas.id ? mapApiCanvas(indexed) : c,
          ),
        }))
        pushToast('Added to chatbot knowledge', {
          description: `${indexed.chunks ?? 0} chunks indexed`,
          kind: 'success',
        })
      } catch (e) {
        updateCanvas(projectId, canvas.id, { status: 'error' })
        pushToast(e instanceof Error ? e.message : 'Re-index failed', { kind: 'danger' })
      }
      return
    }
    updateCanvas(projectId, canvas.id, { status: 'chunking', chunks: 0 })
    window.setTimeout(() => {
      updateCanvas(projectId, canvas.id, { status: 'embedding' })
    }, 600)
    window.setTimeout(() => {
      updateCanvas(projectId, canvas.id, {
        status: 'indexed',
        chunks: 24 + Math.floor(Math.random() * 60),
      })
      pushToast('Added to chatbot knowledge', { kind: 'success' })
    }, 1400)
  }

  const refreshSource = async () => {
    if (!canvas?.sourceUrl || !useApi) return
    try {
      const result = await refreshKnowledgeCanvasSource(projectId, canvas.id)
      replaceCanvases(projectId, (s) => ({
        ...s,
        canvases: s.canvases.map((c) =>
          c.id === canvas.id ? mapApiCanvas(result.canvas) : c,
        ),
      }))
      loadCanvas(mapApiCanvas(result.canvas))
      pushToast(
        result.changed ? 'Source changed — re-indexed' : 'Source up to date',
        { kind: result.changed ? 'warning' : 'success' },
      )
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Refresh failed', { kind: 'danger' })
    }
  }

  const showDiff = async () => {
    if (!canvas || !useApi) {
      setDiffOpen(true)
      setVersions([])
      return
    }
    try {
      const v = await listKnowledgeCanvasVersions(projectId, canvas.id)
      setVersions(v)
      setDiffOpen(true)
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load versions', {
        kind: 'danger',
      })
    }
  }

  const indexRepo = async () => {
    if (!useApi) {
      pushToast('Repo indexing requires an API project with a running sandbox', {
        kind: 'warning',
      })
      return
    }
    setIndexingRepo(true)
    try {
      const result = await indexKnowledgeRepo(projectId)
      const changed = result.created + result.updated
      const matched = result.matched_count ?? result.canvas_ids?.length ?? 0
      if (changed === 0 && matched === 0) {
        pushToast('No docs found to index', {
          description:
            result.message ||
            'Looking for README, AGENTS.md, docs/**, ADR, openapi*, runbooks under the sandbox workspace.',
          kind: 'warning',
        })
      } else if (changed === 0) {
        pushToast('Repo already up to date', {
          description:
            result.message ||
            `${matched} file(s) matched · ${result.skipped} unchanged`,
          kind: 'info',
        })
      } else {
        pushToast('Repo indexed', {
          description: `${result.created} created · ${result.updated} updated · ${result.skipped} skipped`,
          kind: 'success',
        })
      }
      onRefresh?.()
      if (useApi) {
        void listKnowledgeCollections(projectId)
          .then(setCollections)
          .catch(() => undefined)
      }
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Repo index failed', { kind: 'danger' })
    } finally {
      setIndexingRepo(false)
    }
  }

  useEffect(() => {
    if (!useApi) return
    void listKnowledgeCollections(projectId)
      .then(setCollections)
      .catch(() => setCollections([]))
  }, [projectId, useApi, canvases.length])

  const fileInput = (
    <input
      ref={fileRef}
      type="file"
      multiple
      accept=".pdf,.txt,.md,.doc,.docx,application/pdf,text/plain,text/markdown"
      style={{ display: 'none' }}
      onChange={(e) => {
        onUpload(e.target.files)
        e.target.value = ''
      }}
    />
  )

  const createModal = (
    <CreateResourceModal
      isOpen={createOpen}
      title="Create knowledge canvas"
      onClose={() => setCreateOpen(false)}
      onSubmit={() => {
        if (!newName.trim()) return
        if (dirty && canvas) saveCanvas(canvas, { silent: true })
        const id = createCanvas(projectId, { name: newName.trim(), origin: 'created' })
        setActiveId(id)
        setNewName('')
        setCreateOpen(false)
        setMode('edit')
        pushToast('Canvas created', { kind: 'success' })
      }}
      isSubmitDisabled={!newName.trim()}
    >
      <FormGroup label="Name" isRequired fieldId="cv-name">
        <TextInput
          id="cv-name"
          value={newName}
          onChange={(_e, v) => setNewName(v)}
          placeholder="e.g. Architecture notes"
        />
      </FormGroup>
    </CreateResourceModal>
  )

  const collectionModal = (
    <CreateResourceModal
      isOpen={collectionOpen}
      title="Create collection"
      onClose={() => setCollectionOpen(false)}
      onSubmit={() => {
        void (async () => {
          const n = collectionName.trim()
          if (!n) return
          setCollectionSaving(true)
          try {
            const col = await createKnowledgeCollection(projectId, {
              name: n,
              visibility: collectionVisibility,
            })
            setCollections((prev) =>
              prev.some((x) => x.id === col.id) ? prev : [...prev, col],
            )
            if (collectionVisibility === 'agent') {
              const agents = await listProjectAgents(projectId)
              if (agents[0]) {
                await upsertCollectionGrant(projectId, col.id, {
                  agent_id: agents[0].id,
                  can_retrieve: true,
                })
                pushToast('Collection created', {
                  description: `Agent-only · retrieve granted to ${agents[0].name}`,
                  kind: 'success',
                })
              } else {
                pushToast('Collection created', {
                  description: 'Agent-only — create an agent, then grant access from tools',
                  kind: 'success',
                })
              }
            } else {
              pushToast('Collection created', {
                description:
                  collectionVisibility === 'personal'
                    ? 'Visible only to you for retrieval'
                    : 'Shared with the team',
                kind: 'success',
              })
            }
            setCollectionOpen(false)
            setCollectionName('')
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Collection failed', {
              kind: 'danger',
            })
          } finally {
            setCollectionSaving(false)
          }
        })()
      }}
      isSubmitDisabled={!collectionName.trim() || collectionSaving}
    >
      <FormGroup label="Name" isRequired fieldId="col-name">
        <TextInput
          id="col-name"
          value={collectionName}
          onChange={(_e, v) => setCollectionName(v)}
          placeholder="e.g. Onboarding docs"
        />
      </FormGroup>
      <FormGroup label="Visibility" fieldId="col-vis" style={{ marginTop: 12 }}>
        <FormSelect
          id="col-vis"
          value={collectionVisibility}
          onChange={(_e, v) =>
            setCollectionVisibility(v as 'team' | 'personal' | 'agent')
          }
          aria-label="Collection visibility"
        >
          <FormSelectOption value="team" label="Team — shared with project members" />
          <FormSelectOption value="personal" label="Personal — only you" />
          <FormSelectOption value="agent" label="Agent-only — granted agents can retrieve" />
        </FormSelect>
        <p className="lc-meta" style={{ marginTop: 6 }}>
          Collections group canvases for retrieval ACLs. “Repo docs” is created automatically by
          Index repo.
        </p>
      </FormGroup>
    </CreateResourceModal>
  )

  if (canvases.length === 0) {
    return (
      <div className="canvas-empty">
        {fileInput}
        <EmptySplash
          title="No knowledge canvases"
          body="Create a Markdown note for your project, or upload a PDF for Unlimited OCR. Indexing for the chatbot is optional."
          primaryLabel="New canvas"
          onPrimary={() => setCreateOpen(true)}
          secondaryLabel="Upload file"
          onSecondary={() => fileRef.current?.click()}
        />
        {createModal}
        {collectionModal}
      </div>
    )
  }

  const showPipeline = canvas ? isPipelineBusy(canvas.status) : false
  // Unsaved edits on an indexed doc also mean chatbot knowledge is out of date
  const knowledgeDisplay = canvas
    ? chatKnowledgeLabel(canvas.status, {
        bodyDirty: canvas.status === 'indexed' && bodyDirty,
      })
    : null
  const kind = canvas ? kindLabel(canvas.origin) : null
  const actionLabel = canvas
    ? knowledgeActionLabel(
        canvas.status === 'indexed' && bodyDirty ? 'stale' : canvas.status,
      )
    : 'Index'

  return (
    <div className="canvas-shell">
      {fileInput}

      <aside className="canvas-sidebar">
        <div className="canvas-sidebar-toolbar">
          <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
            New
          </Button>
          <Button size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>
            Upload
          </Button>
          <Button
            size="sm"
            variant="secondary"
            isLoading={indexingRepo}
            onClick={() => void indexRepo()}
            title="Index README, docs, ADR, OpenAPI, runbooks from the sandbox"
          >
            Index repo
          </Button>
        </div>
        {useApi ? (
          <div className="canvas-collections">
            <div className="canvas-collections-head">
              <span className="canvas-collections-label">Collections</span>
              <Button
                size="sm"
                variant="plain"
                className="canvas-collections-add"
                onClick={() => {
                  setCollectionName('')
                  setCollectionVisibility('team')
                  setCollectionOpen(true)
                }}
                title="Create collection"
                aria-label="Create collection"
              >
                +
              </Button>
            </div>
            {collections.length === 0 ? (
              <p className="canvas-collections-empty">
                Optional groups for retrieval access
              </p>
            ) : (
              <ul className="canvas-collections-list">
                <li>
                  <button
                    type="button"
                    className={`canvas-collection-row is-filter${filterCollectionId == null ? ' is-active' : ''}`}
                    onClick={() => setFilterCollectionId(null)}
                  >
                    <div className="canvas-collection-text">
                      <span className="canvas-collection-name">All notes</span>
                      <span className="canvas-collection-meta">
                        {canvases.length} canvas{canvases.length === 1 ? '' : 'es'}
                      </span>
                    </div>
                  </button>
                </li>
                {collections.map((c) => {
                  const isRepo = c.name === 'Repo docs'
                  const count = canvases.filter((x) => x.collectionId === c.id).length
                  const meta = isRepo
                    ? 'From Index repo'
                    : c.visibility === 'personal'
                      ? 'Personal'
                      : c.visibility === 'agent'
                        ? 'Agent-only'
                        : 'Team'
                  const active = filterCollectionId === c.id
                  return (
                    <li key={c.id}>
                      <div
                        className={`canvas-collection-row is-filter${active ? ' is-active' : ''}`}
                      >
                        <button
                          type="button"
                          className="canvas-collection-select"
                          title={`Filter: ${c.name} · ${meta}`}
                          onClick={() =>
                            setFilterCollectionId((prev) => (prev === c.id ? null : c.id))
                          }
                        >
                          <span className="canvas-collection-name">{c.name}</span>
                          <span className="canvas-collection-meta">
                            {meta}
                            {count ? ` · ${count}` : ''}
                          </span>
                        </button>
                        {!isRepo ? (
                          <Button
                            size="sm"
                            variant="plain"
                            className="canvas-collection-remove"
                            aria-label={`Delete collection ${c.name}`}
                            title="Delete collection"
                            onClick={() => {
                              void (async () => {
                                if (!window.confirm(`Delete collection “${c.name}”?`)) return
                                try {
                                  await deleteKnowledgeCollection(projectId, c.id)
                                  setCollections((prev) => prev.filter((x) => x.id !== c.id))
                                  if (filterCollectionId === c.id) setFilterCollectionId(null)
                                  // Clear assignment on local canvases for deleted collection
                                  for (const cv of canvases) {
                                    if (cv.collectionId === c.id) {
                                      updateCanvas(projectId, cv.id, { collectionId: undefined })
                                    }
                                  }
                                  pushToast('Collection deleted', { kind: 'info' })
                                } catch (e) {
                                  pushToast(
                                    e instanceof Error ? e.message : 'Delete collection failed',
                                    { kind: 'danger' },
                                  )
                                }
                              })()
                            }}
                            icon={<TimesIcon />}
                          />
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        ) : null}
        <div className="canvas-sidebar-list" role="listbox" aria-label="Canvases">
          {visibleCanvases.length === 0 ? (
            <p className="canvas-collections-empty" style={{ padding: '0.5rem' }}>
              {filterCollectionId
                ? 'No notes in this collection. Open a note and assign it below the title.'
                : 'No canvases yet.'}
            </p>
          ) : null}
          {visibleCanvases.map((c) => {
            const active = c.id === canvas?.id
            const rowUnsaved = active && dirty
            const rowBodyDirty =
              active && bodyDirty
                ? true
                : c.status === 'stale'
            const colName = collectionById(c.collectionId)?.name
            return (
              <button
                key={c.id}
                type="button"
                role="option"
                aria-selected={active}
                className={`canvas-nav-item${active ? ' is-active' : ''}`}
                onClick={() => selectCanvas(c.id)}
              >
                <span className="canvas-nav-title">{c.name}</span>
                <span className="canvas-nav-meta">
                  {colName ? `${colName} · ` : ''}
                  {sidebarMetaLine(c, {
                    unsaved: rowUnsaved,
                    bodyDirty: rowBodyDirty && c.status === 'indexed',
                  })}
                </span>
              </button>
            )
          })}
        </div>
      </aside>

      <section className="canvas-doc">
        {!canvas || !knowledgeDisplay ? (
          <div className="canvas-doc-fallback">
            <p>Select a canvas from the list.</p>
          </div>
        ) : (
          <>
            <header className="canvas-doc-header">
              <div className="canvas-doc-title-row">
                {renaming ? (
                  <div className="canvas-rename-row">
                    <TextInput
                      id="canvas-rename-input"
                      value={renameDraft}
                      onChange={(_e, v) => setRenameDraft(v)}
                      aria-label="Rename canvas"
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
                      aria-label="Rename canvas"
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
                <div className="canvas-doc-status">
                  {kind && (
                    <Label isCompact color="grey" variant="outline">
                      {kind}
                    </Label>
                  )}
                  <Label
                    isCompact
                    color={statusToneColor(knowledgeDisplay.tone)}
                    variant="outline"
                  >
                    {knowledgeDisplay.label}
                  </Label>
                  {canvas.status === 'indexed' && canvas.chunks != null && (
                    <span className="canvas-doc-sub-meta">{canvas.chunks} chunks</span>
                  )}
                  {canvas.sizeLabel && (
                    <span className="canvas-doc-sub-meta">{canvas.sizeLabel}</span>
                  )}
                </div>
              </div>

              <div className="canvas-doc-actions">
                <ToggleGroup className="canvas-mode-toggle" aria-label="Editor mode">
                  <ToggleGroupItem
                    text="Edit"
                    buttonId="canvas-mode-edit"
                    isSelected={mode === 'edit'}
                    onChange={() => setMode('edit')}
                  />
                  <ToggleGroupItem
                    text="Preview"
                    buttonId="canvas-mode-preview"
                    isSelected={mode === 'preview'}
                    onChange={() => setMode('preview')}
                  />
                </ToggleGroup>
                <div className="canvas-doc-action-group">
                  <Button
                    size="sm"
                    variant="primary"
                    isDisabled={!dirty}
                    onClick={() => saveCanvas()}
                    title="Save notes (Ctrl/⌘+S)"
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void reindex()}
                    isDisabled={isPipelineBusy(canvas.status)}
                  >
                    {actionLabel}
                  </Button>
                  <Dropdown
                    isOpen={overflowOpen}
                    onOpenChange={setOverflowOpen}
                    onSelect={() => setOverflowOpen(false)}
                    popperProps={{ position: 'right' }}
                    toggle={(toggleRef) => (
                      <Button
                        ref={toggleRef}
                        size="sm"
                        variant="plain"
                        aria-label="Canvas actions"
                        aria-expanded={overflowOpen}
                        onClick={() => setOverflowOpen((open) => !open)}
                        icon={<EllipsisVIcon />}
                      />
                    )}
                  >
                    <DropdownList>
                      <DropdownItem
                        key="diff"
                        onClick={() => void showDiff()}
                      >
                        Version history / diff
                      </DropdownItem>
                      {canvas.sourceUrl ? (
                        <DropdownItem
                          key="refresh"
                          onClick={() => void refreshSource()}
                        >
                          Refresh from source
                        </DropdownItem>
                      ) : null}
                      <DropdownItem
                        key="stale"
                        onClick={() =>
                          updateCanvas(projectId, canvas.id, { status: 'stale' })
                        }
                      >
                        Mark stale
                      </DropdownItem>
                      <DropdownItem
                        key="delete"
                        isDanger
                        onClick={() => {
                          deleteCanvas(projectId, canvas.id)
                          pushToast('Canvas deleted', { kind: 'info' })
                        }}
                      >
                        Delete
                      </DropdownItem>
                    </DropdownList>
                  </Dropdown>
                </div>
              </div>
              {useApi ? (
                <div className="canvas-collection-assign">
                  <label className="canvas-collection-assign-label" htmlFor="canvas-collection">
                    Collection
                  </label>
                  <FormSelect
                    id="canvas-collection"
                    value={canvas.collectionId || ''}
                    onChange={(_e, v) => assignCollection(v || null)}
                    aria-label="Assign canvas to collection"
                    className="canvas-collection-assign-select"
                  >
                    <FormSelectOption value="" label="None (project default)" />
                    {collections.map((col) => (
                      <FormSelectOption
                        key={col.id}
                        value={col.id}
                        label={
                          col.name === 'Repo docs'
                            ? `${col.name} (Index repo)`
                            : col.name
                        }
                      />
                    ))}
                  </FormSelect>
                  {!collections.length ? (
                    <Button
                      size="sm"
                      variant="link"
                      isInline
                      onClick={() => {
                        setCollectionName('')
                        setCollectionVisibility('team')
                        setCollectionOpen(true)
                      }}
                    >
                      Create a collection
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {canvas.sourceUrl ? (
                <p className="lc-meta" style={{ margin: '0 0 8px' }}>
                  Source:{' '}
                  <a href={canvas.sourceUrl} target="_blank" rel="noreferrer">
                    {canvas.sourceUrl}
                  </a>
                  {canvas.lastFetchedAt
                    ? ` · fetched ${new Date(canvas.lastFetchedAt).toLocaleString()}`
                    : ''}
                </p>
              ) : null}
              {canvas.repoPath ? (
                <p className="lc-meta" style={{ margin: '0 0 8px' }}>
                  Repo path: <code>{canvas.repoPath}</code>
                </p>
              ) : null}
              {diffOpen ? (
                <div className="list-card" style={{ marginBottom: 12 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: 8,
                    }}
                  >
                    <div className="lc-title">Version history</div>
                    <Button size="sm" variant="link" isInline onClick={() => setDiffOpen(false)}>
                      Close
                    </Button>
                  </div>
                  {!versions.length ? (
                    <p className="lc-meta">
                      Current draft vs last saved baseline
                      {bodyDirty ? ' (unsaved changes)' : ' (in sync)'}.
                    </p>
                  ) : (
                    versions.slice(0, 5).map((v) => (
                      <div key={v.id} style={{ marginBottom: 8 }}>
                        <div className="lc-meta">
                          {v.label || 'snapshot'} · {new Date(v.created_at).toLocaleString()}
                        </div>
                        <pre
                          style={{
                            maxHeight: 120,
                            overflow: 'auto',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                          }}
                        >
                          {v.content_md.slice(0, 800)}
                          {v.content_md.length > 800 ? '…' : ''}
                        </pre>
                        <Button
                          size="sm"
                          variant="link"
                          isInline
                          onClick={() => {
                            setDraftMd(v.content_md)
                            setDiffOpen(false)
                          }}
                        >
                          Load into editor
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              ) : null}
              {showPipeline && (
                <EmbedPipeline
                  status={canvas.status}
                  withOcr={canvas.origin === 'ocr' || canvas.mime === 'application/pdf'}
                />
              )}
            </header>

            <div className="canvas-doc-body">
              <MarkdownWorkbench
                value={draftMd}
                mode={mode}
                onChange={(next) => {
                  setDraftMd(next)
                  setSaveState('idle')
                }}
                placeholder={'# Knowledge title\n\nWrite notes the model should know…'}
                ariaLabel={`Markdown for ${canvas.name}`}
              />
            </div>
          </>
        )}
      </section>

      {createModal}
      {collectionModal}
    </div>
  )
}
