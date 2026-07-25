import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  FormGroup,
  Spinner,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { getProject } from '@/data/projects'
import {
  type ApiKnowledgeCanvas,
  type ApiKnowledgeEvalRunResult,
  type ApiKnowledgeEvalSet,
  createKnowledgeEvalSet,
  deleteKnowledgeEvalSet,
  isDemoMode,
  listKnowledgeCanvases,
  listKnowledgeEvalSets,
  runKnowledgeEvalSet,
  updateKnowledgeEvalSet,
} from '@/lib/api'
import { pushToast } from '@/lib/studioToast'

interface EvalTabProps {
  projectId: string
}

type DraftQuestion = {
  key: string
  question: string
  expected_canvas_ids: string[]
}

function uid() {
  return `q-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function EvalTab({ projectId }: EvalTabProps) {
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const [sets, setSets] = useState<ApiKnowledgeEvalSet[]>([])
  const [canvases, setCanvases] = useState<ApiKnowledgeCanvas[]>([])
  const [loading, setLoading] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<ApiKnowledgeEvalRunResult | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [name, setName] = useState('Golden set')
  const [questions, setQuestions] = useState<DraftQuestion[]>([
    { key: uid(), question: '', expected_canvas_ids: [] },
  ])
  const [saving, setSaving] = useState(false)

  const canvasName = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of canvases) m.set(c.id, c.name)
    return m
  }, [canvases])

  const refresh = useCallback(async () => {
    if (!useApi) return
    setLoading(true)
    try {
      const [es, cs] = await Promise.all([
        listKnowledgeEvalSets(projectId),
        listKnowledgeCanvases(projectId),
      ])
      setSets(es)
      setCanvases(cs)
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

  const openCreate = () => {
    setEditingId(null)
    setName('Golden set')
    setQuestions([{ key: uid(), question: '', expected_canvas_ids: [] }])
    setModalOpen(true)
  }

  const openEdit = (s: ApiKnowledgeEvalSet) => {
    setEditingId(s.id)
    setName(s.name)
    setQuestions(
      (s.questions || []).length
        ? (s.questions || []).map((q) => ({
            key: q.id || uid(),
            question: q.question,
            expected_canvas_ids: [...(q.expected_canvas_ids || [])],
          }))
        : [{ key: uid(), question: '', expected_canvas_ids: [] }],
    )
    setModalOpen(true)
  }

  const validQuestions = questions.filter((q) => q.question.trim())

  const onSave = async () => {
    if (!name.trim() || !validQuestions.length) return
    setSaving(true)
    const payload = {
      name: name.trim(),
      questions: validQuestions.map((q) => ({
        question: q.question.trim(),
        expected_canvas_ids: q.expected_canvas_ids,
      })),
    }
    try {
      if (editingId) {
        await updateKnowledgeEvalSet(projectId, editingId, payload)
        pushToast('Eval set updated', { kind: 'success' })
      } else {
        await createKnowledgeEvalSet(projectId, payload)
        pushToast('Eval set created', { kind: 'success' })
      }
      setModalOpen(false)
      await refresh()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Save failed', { kind: 'danger' })
    } finally {
      setSaving(false)
    }
  }

  const onDelete = async (id: string) => {
    if (!window.confirm('Delete this eval set?')) return
    try {
      await deleteKnowledgeEvalSet(projectId, id)
      if (lastRun?.eval_set_id === id) setLastRun(null)
      pushToast('Eval set deleted', { kind: 'info' })
      await refresh()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Delete failed', { kind: 'danger' })
    }
  }

  const onRun = async (id: string) => {
    setRunningId(id)
    try {
      const result = await runKnowledgeEvalSet(projectId, id)
      setLastRun(result)
      pushToast(`Eval score ${(result.score * 100).toFixed(0)}%`, {
        description: `${result.hits}/${result.total} questions retrieved an expected canvas`,
        kind: result.score >= 0.8 ? 'success' : 'warning',
      })
      await refresh()
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Eval run failed', { kind: 'danger' })
    } finally {
      setRunningId(null)
    }
  }

  if (!useApi) {
    return (
      <EmptySplash
        title="Knowledge eval"
        body="Eval sets measure retrieval quality: for each golden question, did the right knowledge canvas appear in the top results? Open an API-backed project with indexed canvases to use this."
      />
    )
  }

  const labelIds = (ids: string[], names?: string[]) => {
    if (names?.length) return names.join(' · ')
    return ids.map((id) => canvasName.get(id) || `${id.slice(0, 8)}…`).join(' · ') || '—'
  }

  return (
    <div className="knowledge-eval-tab">
      <div className="knowledge-eval-intro lc-meta" style={{ marginBottom: 12, maxWidth: 640 }}>
        <strong>What this is:</strong> a recall test for RAG. Write questions you expect the agent
        to answer from specific canvases, pick those canvases, then Run. Score is how often an
        expected canvas appears in the top retrieval hits — not whether free-text answers are
        correct.
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Button variant="primary" onClick={openCreate}>
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
          body="Add golden questions and mark which canvases should be retrieved. Re-run after indexing repo docs or pinning web sources."
          primaryLabel="New eval set"
          onPrimary={openCreate}
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
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <Button
              size="sm"
              variant="primary"
              isLoading={runningId === s.id}
              onClick={() => void onRun(s.id)}
            >
              Run
            </Button>
            <Button size="sm" variant="secondary" onClick={() => openEdit(s)}>
              Edit
            </Button>
            <Button size="sm" variant="danger" onClick={() => void onDelete(s.id)}>
              Delete
            </Button>
          </div>
        </div>
      ))}
      {lastRun ? (
        <div style={{ marginTop: 16 }}>
          <div className="lc-title">Last run</div>
          <div className="lc-meta" style={{ marginBottom: 8 }}>
            Score {(lastRun.score * 100).toFixed(0)}% ({lastRun.hits}/{lastRun.total} hit)
          </div>
          {lastRun.results.map((r) => (
            <div key={r.question_id} className="list-card">
              <div className="lc-title" style={{ fontSize: 13 }}>
                {r.hit ? '✓' : '✗'} {r.question}
              </div>
              <div className="lc-meta">
                Expected: {labelIds(r.expected_canvas_ids || [], r.expected_names)}
              </div>
              <div className="lc-meta">
                Retrieved: {labelIds(r.retrieved_canvas_ids || [], r.retrieved_names)}
              </div>
              {typeof r.top_score === 'number' ? (
                <div className="lc-meta">Top score: {r.top_score.toFixed(3)}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <CreateResourceModal
        isOpen={modalOpen}
        title={editingId ? 'Edit eval set' : 'Create eval set'}
        onClose={() => setModalOpen(false)}
        onSubmit={() => void onSave()}
        isSubmitDisabled={!name.trim() || !validQuestions.length || saving}
        submitLabel={editingId ? 'Save' : 'Create'}
      >
        <FormGroup label="Name" isRequired fieldId="eval-name">
          <TextInput id="eval-name" value={name} onChange={(_e, v) => setName(v)} />
        </FormGroup>
        <div style={{ marginTop: 12 }}>
          <div className="lc-title" style={{ fontSize: 13, marginBottom: 8 }}>
            Questions
          </div>
          {questions.map((q, idx) => (
            <div
              key={q.key}
              style={{
                border: '1px solid var(--pf-t--global--border--color--default, #d2d2d2)',
                borderRadius: 6,
                padding: 10,
                marginBottom: 10,
              }}
            >
              <FormGroup label={`Question ${idx + 1}`} fieldId={`eval-q-${q.key}`}>
                <TextArea
                  id={`eval-q-${q.key}`}
                  value={q.question}
                  rows={2}
                  onChange={(_e, v) =>
                    setQuestions((prev) =>
                      prev.map((x) => (x.key === q.key ? { ...x, question: v } : x)),
                    )
                  }
                  placeholder="What does the architecture doc say about RAG?"
                />
              </FormGroup>
              <div className="lc-meta" style={{ margin: '8px 0 4px' }}>
                Expected canvases (should be retrieved)
              </div>
              {!canvases.length ? (
                <div className="lc-meta">No canvases yet — create or index knowledge first.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 160, overflow: 'auto' }}>
                  {canvases.map((c) => {
                    const checked = q.expected_canvas_ids.includes(c.id)
                    return (
                      <Checkbox
                        key={c.id}
                        id={`eval-${q.key}-${c.id}`}
                        label={c.name}
                        isChecked={checked}
                        onChange={(_e, isChecked) => {
                          setQuestions((prev) =>
                            prev.map((x) => {
                              if (x.key !== q.key) return x
                              const ids = new Set(x.expected_canvas_ids)
                              if (isChecked) ids.add(c.id)
                              else ids.delete(c.id)
                              return { ...x, expected_canvas_ids: [...ids] }
                            }),
                          )
                        }}
                      />
                    )
                  })}
                </div>
              )}
              {questions.length > 1 ? (
                <Button
                  size="sm"
                  variant="link"
                  isInline
                  style={{ marginTop: 6 }}
                  onClick={() => setQuestions((prev) => prev.filter((x) => x.key !== q.key))}
                >
                  Remove question
                </Button>
              ) : null}
            </div>
          ))}
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              setQuestions((prev) => [
                ...prev,
                { key: uid(), question: '', expected_canvas_ids: [] },
              ])
            }
          >
            Add question
          </Button>
        </div>
      </CreateResourceModal>
    </div>
  )
}
