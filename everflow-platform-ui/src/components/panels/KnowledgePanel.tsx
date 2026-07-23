import { useCallback, useEffect, useState } from 'react'
import { Tabs, Tab, TabTitleText } from '@patternfly/react-core'
import { getProject } from '@/data/projects'
import {
  createKnowledgeCanvas,
  deleteKnowledgeCanvas,
  getKnowledgeCanvas,
  isDemoMode,
  listKnowledgeCanvases,
  updateKnowledgeCanvas,
} from '@/lib/api'
import { mapApiCanvas } from '@/lib/studioMap'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { KnowledgeCanvas } from '@/types/studio'
import { CanvasTab } from './knowledge/CanvasTab'
import { MindMapsTab } from './knowledge/MindMapsTab'
import { WebSearchTab } from './knowledge/WebSearchTab'

export function KnowledgePanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const demoState = useProjectStudio(projectId)
  const replaceCanvases = useStudioDemoStore((s) => s.update)

  const [sub, setSub] = useState<'canvas' | 'web' | 'mind'>('canvas')
  const [loading, setLoading] = useState(false)

  const refreshApi = useCallback(async () => {
    if (!useApi) return
    setLoading(true)
    try {
      const list = await listKnowledgeCanvases(projectId)
      const full = await Promise.all(
        list.map(async (c) => {
          try {
            return mapApiCanvas(await getKnowledgeCanvas(projectId, c.id))
          } catch {
            return mapApiCanvas(c)
          }
        }),
      )
      replaceCanvases(projectId, (s) => ({ ...s, canvases: full }))
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

  useEffect(() => {
    if (!useApi) return

    const prev = useStudioDemoStore.getState()
    const prevCreate = prev.createCanvas
    const prevUpdate = prev.updateCanvas
    const prevDelete = prev.deleteCanvas

    useStudioDemoStore.setState({
      createCanvas: (pid, data) => {
        if (pid !== projectId) return prevCreate(pid, data)
        const localId = prevCreate(pid, data)
        void (async () => {
          try {
            const created = await createKnowledgeCanvas(pid, {
              name: data.name,
              description: data.desc,
              content_md: data.contentMd ?? '',
              origin: data.origin ?? 'created',
            })
            const mapped = mapApiCanvas(created)
            useStudioDemoStore.getState().update(pid, (s) => ({
              ...s,
              canvases: s.canvases.map((c) => (c.id === localId ? mapped : c)),
            }))
          } catch (e) {
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
        void (async () => {
          try {
            await updateKnowledgeCanvas(pid, id, {
              name: patch.name,
              content_md: patch.contentMd,
              description: patch.desc,
              status: patch.status,
            })
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
      useStudioDemoStore.setState({
        createCanvas: prevCreate,
        updateCanvas: prevUpdate,
        deleteCanvas: prevDelete,
      })
    }
  }, [projectId, refreshApi, useApi])

  const canvases: KnowledgeCanvas[] = demoState.canvases

  return (
    <div className="knowledge-panel-root">
      <div className="panel-toolbar">
        <Tabs
          activeKey={sub}
          onSelect={(_e, k) => setSub(k as typeof sub)}
          variant="secondary"
          className="panel-pf-tabs"
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
        </Tabs>
      </div>
      <div
        className={
          sub === 'canvas' || sub === 'mind'
            ? 'knowledge-panel-body knowledge-panel-body--fill'
            : 'panel-scroll knowledge-panel-body'
        }
      >
        {sub === 'canvas' && <CanvasTab projectId={projectId} canvases={canvases} />}
        {sub === 'web' && <WebSearchTab projectId={projectId} />}
        {sub === 'mind' && <MindMapsTab projectId={projectId} mindMaps={demoState.mindMaps} />}
      </div>
    </div>
  )
}
