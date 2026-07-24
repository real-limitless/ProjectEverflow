import { useCallback, useEffect, useState } from 'react'
import { Button, FormGroup, Spinner, TextArea, TextInput } from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { getProject } from '@/data/projects'
import {
  type ApiKnowledgeEvalRunResult,
  type ApiKnowledgeEvalSet,
  createKnowledgeEvalSet,
  isDemoMode,
  listKnowledgeCanvases,
  listKnowledgeEvalSets,
  runKnowledgeEvalSet,
} from '@/lib/api'
import { pushToast } from '@/lib/studioToast'

interface EvalTabProps {
  projectId: string
}

export function EvalTab({ projectId }: EvalTabProps) {
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const [sets, setSets] = useState<ApiKnowledgeEvalSet[]>([])
  const [loading, setLoading] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<ApiKnowledgeEvalRunResult | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('Golden set')
  const [questionsText, setQuestionsText] = useState('')
  const [canvasIds, setCanvasIds] = useState<string[]>([])

  const refresh = useCallback(async () => {
    if (!useApi) return
    setLoading(true)
    try {
      const [es, canvases] = await Promise.all([
        listKnowledgeEvalSets(projectId),
        listKnowledgeCanvases(projectId),
      ])
      setSets(es)
      setCanvasIds(canvases.map((c) => c.id))
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load eval sets', {
        kind: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId, useApi])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (!useApi) {
    return (
      <EmptySplash
        title="Knowledge eval"
        body="Eval sets run against live retrieval. Open an API-backed project to create golden questions and score recall."
      />
    )
  }

  const onCreate = async () => {
    const lines = questionsText
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    if (!name.trim() || !lines.length) return
    try {
      await createKnowledgeEvalSet(projectId, {
        name: name.trim(),
        questions: lines.map((question) => ({
          question,
          expected_canvas_ids: canvasIds.slice(0, 1),
        })),
      })
      setCreateOpen(false)
      setQuestionsText('')
      pushToast('Eval set created', { kind: 'success' })
      await refresh()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Create failed', { kind: 'danger' })
    }
  }

  const onRun = async (id: string) => {
    setRunningId(id)
    try {
      const result = await runKnowledgeEvalSet(projectId, id)
      setLastRun(result)
      pushToast(`Eval score ${(result.score * 100).toFixed(0)}%`, {
        description: `${result.hits}/${result.total} hit`,
        kind: result.score >= 0.8 ? 'success' : 'warning',
      })
      await refresh()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Eval run failed', { kind: 'danger' })
    } finally {
      setRunningId(null)
    }
  }

  return (
    <div className="knowledge-eval-tab">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          New eval set
        </Button>
        <Button variant="secondary" onClick={() => void refresh()} isDisabled={loading}>
          Refresh
        </Button>
      </div>
      {loading ? (
        <div className="reader-mode-loading">
          <Spinner size="md" />
        </div>
      ) : null}
      {!loading && !sets.length ? (
        <EmptySplash
          title="No eval sets"
          body="Add golden questions that should retrieve specific canvases. Run to score recall@k."
        />
      ) : null}
      {sets.map((s) => (
        <div className="list-card" key={s.id}>
          <div className="lc-title">{s.name}</div>
          <div className="lc-meta">
            {(s.questions || []).length} questions
            {typeof s.last_score === 'number'
              ? ` · last ${(s.last_score * 100).toFixed(0)}%`
              : ''}
            {s.last_run_at ? ` · ${new Date(s.last_run_at).toLocaleString()}` : ''}
          </div>
          <Button
            size="sm"
            variant="primary"
            style={{ marginTop: 8 }}
            isLoading={runningId === s.id}
            onClick={() => void onRun(s.id)}
          >
            Run
          </Button>
        </div>
      ))}
      {lastRun ? (
        <div style={{ marginTop: 16 }}>
          <div className="lc-title">Last run</div>
          <div className="lc-meta" style={{ marginBottom: 8 }}>
            Score {(lastRun.score * 100).toFixed(0)}% ({lastRun.hits}/{lastRun.total})
          </div>
          {lastRun.results.map((r) => (
            <div key={r.question_id} className="list-card">
              <div className="lc-title" style={{ fontSize: 13 }}>
                {r.hit ? '✓' : '✗'} {r.question}
              </div>
              <div className="lc-meta">
                expected: {(r.expected_canvas_ids || []).join(', ') || '—'}
              </div>
              <div className="lc-meta">
                retrieved: {(r.retrieved_canvas_ids || []).join(', ') || '—'}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      <CreateResourceModal
        isOpen={createOpen}
        title="Create eval set"
        onClose={() => setCreateOpen(false)}
        onSubmit={() => void onCreate()}
        isSubmitDisabled={!name.trim() || !questionsText.trim()}
      >
        <FormGroup label="Name" isRequired fieldId="eval-name">
          <TextInput
            id="eval-name"
            value={name}
            onChange={(_e, v) => setName(v)}
          />
        </FormGroup>
        <FormGroup
          label="Questions (one per line)"
          isRequired
          fieldId="eval-qs"
          style={{ marginTop: 12 }}
        >
          <TextArea
            id="eval-qs"
            value={questionsText}
            onChange={(_e, v) => setQuestionsText(v)}
            rows={6}
            placeholder="What does the architecture doc say about RAG?"
          />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
