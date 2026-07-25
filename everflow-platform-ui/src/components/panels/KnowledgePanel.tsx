import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import SyncAltIcon from '@patternfly/react-icons/dist/esm/icons/sync-alt-icon'
import { getProject } from '@/data/projects'
import {
  createKnowledgeCanvas,
  createKnowledgeMindMap,
  deleteKnowledgeCanvas,
  deleteKnowledgeMindMap,
  getKnowledgeCanvas,
  isDemoMode,
  listKnowledgeCanvases,
  listKnowledgeMindMaps,
  updateKnowledgeCanvas,
  updateKnowledgeMindMap,
} from '@/lib/api'
import { mapApiCanvas } from '@/lib/studioMap'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { KnowledgeCanvas } from '@/types/studio'
import { CanvasTab } from './knowledge/CanvasTab'
import { EvalTab } from './knowledge/EvalTab'
import { GraphTab } from './knowledge/GraphTab'
import { MindMapsTab } from './knowledge/MindMapsTab'
import { WebSearchTab } from './knowledge/WebSearchTab'

/** Server canvas ids are UUIDs; optimistic demo ids look like `cv-…`. */
function isServerCanvasId(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
}

export function KnowledgePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const demoState = useProjectStudio(projectId)
  const replaceCanvases = useStudioDemoStore((s) => s.update)

  const [sub, setSub] = useState<'canvas' | 'web' | 'mind' | 'graph' | 'eval'>('canvas')
  const [loading, setLoading] = useState(false)

  /** Patches applied while an optimistic create POST is still in flight. */
  const pendingPatchesRef = useRef(
    new Map<string, Partial<KnowledgeCanvas>[]>(),
  )

  const refreshApi = useCallback(async () => {
    if (!useApi) return
    setLoading(true)
    try {
      const [list, mindMaps] = await Promise.all([
        listKnowledgeCanvases(projectId),
        listKnowledgeMindMaps(projectId).catch(() => []),
      ])
      const full = await Promise.all(
        list.map(async (c) => {
          try {
            return mapApiCanvas(await getKnowledgeCanvas(projectId, c.id))
          } catch {
            return mapApiCanvas(c)
          }
        }),
      )
      replaceCanvases(projectId, (s) => ({
        ...s,
        canvases: full,
        mindMaps: mindMaps.map((m) => ({
          id: m.id,
          name: m.name,
          mermaid: m.mermaid,
          updatedAt: m.updated_at,
        })),
      }))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load knowledge canvases', {
        kind: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId, replaceCanvases, useApi])

  useEffect(() => {
    void refreshApi()
  }, [refreshApi])

  // Re-fetch when tab regains focus / becomes visible (chat/MCP may have created canvases)
  useEffect(() => {
    if (!useApi) return
    let t: number | null = null
    const debounced = () => {
      if (t != null) window.clearTimeout(t)
      t = window.setTimeout(() => {
        void refreshApi()
      }, 400)
    }
    const onVis = () => {
      if (document.visibilityState === 'visible') debounced()
    }
    window.addEventListener('focus', debounced)
    document.addEventListener('visibilitychange', onVis)
    const poll = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refreshApi()
    }, 20_000)
    return () => {
      if (t != null) window.clearTimeout(t)
      window.removeEventListener('focus', debounced)
      document.removeEventListener('visibilitychange', onVis)
      window.clearInterval(poll)
    }
  }, [refreshApi, useApi])

  useEffect(() => {
    if (!useApi) return

    const prev = useStudioDemoStore.getState()
    const prevCreate = prev.createCanvas
    const prevUpdate = prev.updateCanvas
    const prevDelete = prev.deleteCanvas
    const prevCreateMm = prev.createMindMap
    const prevUpdateMm = prev.updateMindMap
    const prevDeleteMm = prev.deleteMindMap
    const pendingPatches = pendingPatchesRef.current

    useStudioDemoStore.setState({
      createMindMap: (pid, name, mermaid) => {
        if (pid !== projectId) return prevCreateMm(pid, name, mermaid)
        const localId = prevCreateMm(pid, name, mermaid)
        void (async () => {
          try {
            const created = await createKnowledgeMindMap(pid, {
              name,
              mermaid: mermaid ?? '',
            })
            useStudioDemoStore.getState().update(pid, (s) => ({
              ...s,
              mindMaps: s.mindMaps.map((m) =>
                m.id === localId
                  ? {
                      id: created.id,
                      name: created.name,
                      mermaid: created.mermaid,
                      updatedAt: created.updated_at,
                    }
                  : m,
              ),
            }))
          } catch (e) {
            prevDeleteMm(pid, localId)
            pushToast(e instanceof Error ? e.message : 'Create mind map failed', {
              kind: 'danger',
            })
          }
        })()
        return localId
      },
      updateMindMap: (pid, id, patch) => {
        if (pid !== projectId) {
          prevUpdateMm(pid, id, patch)
          return
        }
        prevUpdateMm(pid, id, patch)
        if (!isServerCanvasId(id)) return
        void (async () => {
          try {
            await updateKnowledgeMindMap(pid, id, {
              name: patch.name,
              mermaid: patch.mermaid,
            })
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Save mind map failed', {
              kind: 'danger',
            })
          }
        })()
      },
      deleteMindMap: (pid, id) => {
        if (pid !== projectId) {
          prevDeleteMm(pid, id)
          return
        }
        prevDeleteMm(pid, id)
        if (!isServerCanvasId(id)) return
        void (async () => {
          try {
            await deleteKnowledgeMindMap(pid, id)
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Delete mind map failed', {
              kind: 'danger',
            })
            await refreshApi()
          }
        })()
      },
      createCanvas: (pid, data) => {
        if (pid !== projectId) return prevCreate(pid, data)
        const localId = prevCreate(pid, data)
        pendingPatches.set(localId, [])
        void (async () => {
          try {
            const sourceUrl =
              data.origin === 'web' && data.desc?.startsWith('http')
                ? data.desc
                : undefined
            const created = await createKnowledgeCanvas(pid, {
              name: data.name.slice(0, 200),
              description: data.desc,
              content_md: data.contentMd ?? '',
              origin: data.origin ?? 'created',
              source_url: sourceUrl,
            })
            const mapped = mapApiCanvas(created)
            const queued = pendingPatches.get(localId) ?? []
            pendingPatches.delete(localId)
            const merged = queued.reduce<KnowledgeCanvas>(
              (acc, patch) => ({ ...acc, ...patch, updatedAt: 'just now' }),
              mapped,
            )
            useStudioDemoStore.getState().update(pid, (s) => ({
              ...s,
              canvases: s.canvases.map((c) => (c.id === localId ? merged : c)),
            }))
            const statusPatch =
              merged.status !== mapped.status || merged.chunks !== mapped.chunks
            if (statusPatch) {
              try {
                await updateKnowledgeCanvas(pid, mapped.id, {
                  status: merged.status,
                  // chunks may not be on update body — status is enough for sync
                })
              } catch {
                // Local state already correct; ignore sync race
              }
            }
          } catch (e) {
            pendingPatches.delete(localId)
            prevDelete(pid, localId)
            pushToast(e instanceof Error ? e.message : 'Create canvas failed', { kind: 'danger' })
          }
        })()
        return localId
      },
      updateCanvas: (pid, id, patch) => {
        if (pid !== projectId) {
          prevUpdate(pid, id, patch)
          return
        }
        prevUpdate(pid, id, patch)
        if (!isServerCanvasId(id)) {
          const q = pendingPatches.get(id)
          if (q) q.push(patch)
          return
        }
        void (async () => {
          try {
            const body: {
              name?: string
              content_md?: string
              description?: string | null
              status?: string
              collection_id?: string | null
            } = {
              name: patch.name,
              content_md: patch.contentMd,
              description: patch.desc,
              status: patch.status,
            }
            if ('collectionId' in patch) {
              body.collection_id = patch.collectionId ?? null
            }
            await updateKnowledgeCanvas(pid, id, body)
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Save canvas failed', { kind: 'danger' })
            await refreshApi()
          }
        })()
      },
      deleteCanvas: (pid, id) => {
        if (pid !== projectId) {
          prevDelete(pid, id)
          return
        }
        prevDelete(pid, id)
        pendingPatches.delete(id)
        if (!isServerCanvasId(id)) return
        void (async () => {
          try {
            await deleteKnowledgeCanvas(pid, id)
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Delete canvas failed', { kind: 'danger' })
            await refreshApi()
          }
        })()
      },
    })

    return () => {
      pendingPatches.clear()
      useStudioDemoStore.setState({
        createCanvas: prevCreate,
        updateCanvas: prevUpdate,
        deleteCanvas: prevDelete,
        createMindMap: prevCreateMm,
        updateMindMap: prevUpdateMm,
        deleteMindMap: prevDeleteMm,
      })
    }
  }, [projectId, refreshApi, useApi])

  const canvases: KnowledgeCanvas[] = demoState.canvases

  return (
    <div className="knowledge-panel-root">
      <div className="panel-toolbar" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
          style={{ flex: 1, minWidth: 0 }}
        >
          <Tab
            eventKey="canvas"
            title={
              <TabTitleText>
                Canvas{useApi && loading ? '…' : ` (${canvases.length})`}
              </TabTitleText>
            }
          />
          <Tab eventKey="web" title={<TabTitleText>Web search</TabTitleText>} />
          <Tab eventKey="mind" title={<TabTitleText>Mind maps</TabTitleText>} />
          <Tab eventKey="graph" title={<TabTitleText>Graph</TabTitleText>} />
          <Tab eventKey="eval" title={<TabTitleText>Eval</TabTitleText>} />
        </Tabs>
        {useApi ? (
          <Button
            size="sm"
            variant="secondary"
            icon={<SyncAltIcon />}
            isLoading={loading}
            onClick={() => void refreshApi()}
            title="Refresh knowledge from server (use after chat creates canvases)"
            aria-label="Refresh knowledge"
          >
            Refresh
          </Button>
        ) : null}
      </div>
      <div
        className={
          sub === 'canvas' || sub === 'mind' || sub === 'web' || sub === 'graph'
            ? 'knowledge-panel-body knowledge-panel-body--fill'
            : 'panel-scroll knowledge-panel-body'
        }
      >
        {sub === 'canvas' && (
          <CanvasTab
            projectId={projectId}
            canvases={canvases}
            onRefresh={() => void refreshApi()}
          />
        )}
        {sub === 'web' && <WebSearchTab projectId={projectId} />}
        {sub === 'mind' && <MindMapsTab projectId={projectId} mindMaps={demoState.mindMaps} />}
        {sub === 'graph' && <GraphTab projectId={projectId} />}
        {sub === 'eval' && <EvalTab projectId={projectId} />}
      </div>
    </div>
  )
}
