import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  ExpandableSection,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Spinner,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import { isDemoMode } from '@/lib/api'
import {
  createJob as createApiJob,
  deleteJob as deleteApiJob,
  getJobLogs,
  listJobs,
  restartJob as restartApiJob,
  startJob as startApiJob,
  stopJob as stopApiJob,
  updateJob as updateApiJob,
  type ApiJob,
} from '@/lib/jobsApi'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { BackgroundJob, JobStatus } from '@/types/studio'
import { StatusLabel } from './statusLabel'

const LIST_POLL_MS = 4000
const LOG_POLL_MS = 2500
const LOG_TAIL = 200

function mapApiStatus(status: string): JobStatus {
  switch (status) {
    case 'running':
      return 'run'
    case 'queued':
      return 'queued'
    case 'exited':
      return 'ok'
    case 'killed':
      return 'cancelled'
    case 'error':
      return 'err'
    default:
      return status === 'ok' || status === 'err' || status === 'cancelled' || status === 'run'
        ? status
        : 'queued'
  }
}

function statusLabel(status: string): string {
  if (status === 'running' || status === 'run') return 'running'
  if (status === 'exited' || status === 'ok') return 'exited'
  if (status === 'killed' || status === 'cancelled') return 'stopped'
  if (status === 'error' || status === 'err') return 'error'
  return status
}

function isRunningStatus(status: string): boolean {
  return status === 'running' || status === 'run' || status === 'queued'
}

function isStoppedStatus(status: string): boolean {
  return (
    status === 'exited' ||
    status === 'ok' ||
    status === 'killed' ||
    status === 'cancelled' ||
    status === 'error' ||
    status === 'err'
  )
}

export function JobsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const catalogVersion = usePlaygroundStore((s) => s.catalogVersion)
  const project = getProject(projectId === 'default' ? null : projectId)
  void catalogVersion

  const useApi = Boolean(project?.fromApi) && !isDemoMode()
  const sandboxRunning = project?.sandboxStatus === 'running'

  const demoJobs = useProjectStudio(projectId).jobs
  const createDemoJob = useStudioDemoStore((s) => s.createJob)
  const killDemoJob = useStudioDemoStore((s) => s.killJob)
  const updateDemoJob = useStudioDemoStore((s) => s.updateJob)
  const deleteDemoJob = useStudioDemoStore((s) => s.deleteJob)
  const startDemoJob = useStudioDemoStore((s) => s.startJob)
  const restartDemoJob = useStudioDemoStore((s) => s.restartJob)

  const [apiJobs, setApiJobs] = useState<ApiJob[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [logsById, setLogsById] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  const [open, setOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [command, setCommand] = useState('npm run dev')
  const [cwd, setCwd] = useState('')
  // Demo-only fields
  const [type, setType] = useState('custom')
  const [schedule, setSchedule] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const refreshList = useCallback(async () => {
    if (!useApi || !projectId || !sandboxRunning) {
      setApiJobs([])
      return
    }
    try {
      const rows = await listJobs(projectId)
      setApiJobs(rows)
    } catch {
      /* keep last good list */
    }
  }, [useApi, projectId, sandboxRunning])

  useEffect(() => {
    if (!useApi) return
    setLoading(true)
    void refreshList().finally(() => setLoading(false))
    const id = window.setInterval(() => void refreshList(), LIST_POLL_MS)
    return () => window.clearInterval(id)
  }, [useApi, refreshList])

  useEffect(() => {
    if (!useApi || !projectId || !expandedId || !sandboxRunning) return
    let cancelled = false
    const pull = async () => {
      try {
        const logs = await getJobLogs(projectId, expandedId, LOG_TAIL)
        if (!cancelled) {
          setLogsById((prev) => ({ ...prev, [expandedId]: logs.content }))
        }
      } catch {
        /* ignore */
      }
    }
    void pull()
    const id = window.setInterval(() => void pull(), LOG_POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [useApi, projectId, expandedId, sandboxRunning])

  const resetForm = () => {
    setEditingId(null)
    setTitle('')
    setCommand('npm run dev')
    setCwd('')
    setType('custom')
    setSchedule('')
  }

  const openCreate = () => {
    resetForm()
    setOpen(true)
  }

  const openEditApi = (job: ApiJob) => {
    setEditingId(job.id)
    setTitle(job.title)
    setCommand(job.command)
    setCwd(job.cwd || '')
    setOpen(true)
  }

  const openEditDemo = (job: BackgroundJob) => {
    setEditingId(job.id)
    setTitle(job.title)
    setType(job.type)
    setSchedule(job.schedule || '')
    setCommand(job.command || 'npm run dev')
    setCwd(job.cwd || '')
    setOpen(true)
  }

  const submit = async () => {
    if (!title.trim()) return
    if (useApi) {
      if (!sandboxRunning) {
        pushToast('Sandbox must be running to manage jobs', { kind: 'warning' })
        return
      }
      if (!command.trim()) return
      setSubmitting(true)
      try {
        if (editingId) {
          const running = apiJobs.some((j) => j.id === editingId && j.status === 'running')
          const job = await updateApiJob(
            projectId,
            editingId,
            running
              ? { title: title.trim() }
              : {
                  title: title.trim(),
                  command: command.trim(),
                  cwd: cwd.trim() || '/workspace',
                },
          )
          setApiJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)))
          pushToast('Job updated', { description: job.title, kind: 'success' })
        } else {
          const job = await createApiJob(projectId, {
            title: title.trim(),
            command: command.trim(),
            ...(cwd.trim() ? { cwd: cwd.trim() } : {}),
          })
          setApiJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)])
          pushToast('Job started', {
            description: `${job.title} · pid ${job.pid ?? '?'}`,
            kind: 'success',
          })
          setExpandedId(job.id)
        }
        resetForm()
        setOpen(false)
      } catch (err) {
        pushToast(editingId ? 'Failed to update job' : 'Failed to start job', {
          description: err instanceof Error ? err.message : 'Unknown error',
          kind: 'danger',
        })
      } finally {
        setSubmitting(false)
      }
      return
    }

    if (editingId) {
      updateDemoJob(projectId, editingId, {
        title: title.trim(),
        type,
        schedule: schedule || undefined,
      })
      pushToast('Job updated', { description: title.trim(), kind: 'success' })
    } else {
      createDemoJob(projectId, {
        title: title.trim(),
        type,
        schedule: schedule || undefined,
      })
      pushToast('Job created', { description: `${title.trim()} queued`, kind: 'success' })
    }
    resetForm()
    setOpen(false)
  }

  const runApiAction = async (
    job: ApiJob,
    action: 'stop' | 'start' | 'restart' | 'remove',
  ) => {
    setBusyId(job.id)
    try {
      if (action === 'stop') {
        const updated = await stopApiJob(projectId, job.id)
        setApiJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
        pushToast('Job stopped', { description: job.title, kind: 'warning' })
      } else if (action === 'start') {
        const updated = await startApiJob(projectId, job.id)
        setApiJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
        pushToast('Job started', {
          description: `${job.title} · pid ${updated.pid ?? '?'}`,
          kind: 'success',
        })
        setExpandedId(job.id)
      } else if (action === 'restart') {
        const updated = await restartApiJob(projectId, job.id)
        setApiJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
        pushToast('Job restarted', {
          description: `${job.title} · pid ${updated.pid ?? '?'}`,
          kind: 'success',
        })
        setExpandedId(job.id)
      } else {
        await deleteApiJob(projectId, job.id)
        setApiJobs((prev) => prev.filter((j) => j.id !== job.id))
        if (expandedId === job.id) setExpandedId(null)
        pushToast('Job removed', { description: job.title, kind: 'warning' })
      }
    } catch (err) {
      pushToast(`Failed to ${action} job`, {
        description: err instanceof Error ? err.message : 'Unknown error',
        kind: 'danger',
      })
    } finally {
      setBusyId(null)
    }
  }

  const jobs = useApi ? apiJobs : demoJobs
  const canCreate = useApi ? sandboxRunning : true
  const editingRunning =
    useApi &&
    Boolean(editingId) &&
    apiJobs.some((j) => j.id === editingId && j.status === 'running')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          Background jobs
        </span>
        <Button variant="primary" size="sm" onClick={openCreate} isDisabled={!canCreate}>
          Create job
        </Button>
      </div>
      <div className="panel-scroll">
        {useApi && !sandboxRunning ? (
          <EmptySplash
            title="Sandbox not running"
            body="Start the project sandbox to create and manage background jobs."
          />
        ) : loading && useApi && jobs.length === 0 ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
            <Spinner size="lg" />
          </div>
        ) : jobs.length === 0 ? (
          <EmptySplash
            title="No background jobs"
            body="Create a job to run a long-lived command in the sandbox (for example npm run dev)."
            primaryLabel={canCreate ? 'Create job' : undefined}
            onPrimary={canCreate ? openCreate : undefined}
          />
        ) : useApi ? (
          apiJobs.map((j) => {
            const uiStatus = mapApiStatus(j.status)
            const isExpanded = expandedId === j.id
            const running = isRunningStatus(j.status)
            const stopped = isStoppedStatus(j.status)
            const busy = busyId === j.id
            return (
              <div className="list-card" key={j.id}>
                <div className="lc-row">
                  <div className="lc-title">{j.title}</div>
                  <StatusLabel status={uiStatus} text={statusLabel(j.status)} />
                </div>
                <div className="lc-meta">
                  <code style={{ fontSize: 12 }}>{j.command}</code>
                  {j.cwd ? ` · ${j.cwd}` : ''}
                  {j.pid != null && running ? ` · pid ${j.pid}` : ''}
                </div>
                <div
                  style={{
                    marginTop: 8,
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  {running && (
                    <Button
                      variant="secondary"
                      size="sm"
                      isDisabled={busy}
                      onClick={() => void runApiAction(j, 'stop')}
                    >
                      Stop
                    </Button>
                  )}
                  {stopped && (
                    <Button
                      variant="secondary"
                      size="sm"
                      isDisabled={busy}
                      onClick={() => void runApiAction(j, 'start')}
                    >
                      Start
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    isDisabled={busy}
                    onClick={() => void runApiAction(j, 'restart')}
                  >
                    Restart
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    isDisabled={busy}
                    onClick={() => openEditApi(j)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    isDisabled={busy}
                    onClick={() => void runApiAction(j, 'remove')}
                  >
                    Remove
                  </Button>
                </div>
                <div style={{ marginTop: 8 }}>
                  <ExpandableSection
                    toggleText={isExpanded ? 'Hide logs' : 'Show logs'}
                    isExpanded={isExpanded}
                    onToggle={(_e, v) => setExpandedId(v ? j.id : null)}
                  >
                    <pre
                      className="wf-params-pre"
                      style={{
                        maxHeight: 220,
                        overflow: 'auto',
                        marginTop: 8,
                        fontSize: 11,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {logsById[j.id] ?? (isExpanded ? 'Loading…' : '')}
                    </pre>
                  </ExpandableSection>
                </div>
              </div>
            )
          })
        ) : (
          demoJobs.map((j) => {
            const running = isRunningStatus(j.status)
            const stopped = isStoppedStatus(j.status)
            return (
              <div className="list-card" key={j.id}>
                <div className="lc-row">
                  <div className="lc-title">{j.title}</div>
                  <StatusLabel status={j.status} />
                </div>
                <div className="lc-meta">
                  {j.type}
                  {j.schedule ? ` · ${j.schedule}` : ''} · {j.progress}
                </div>
                <div
                  style={{
                    marginTop: 8,
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  {running && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        killDemoJob(projectId, j.id)
                        pushToast('Job stopped', {
                          description: j.title,
                          kind: 'warning',
                        })
                      }}
                    >
                      Stop
                    </Button>
                  )}
                  {stopped && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        startDemoJob(projectId, j.id)
                        pushToast('Job started', {
                          description: j.title,
                          kind: 'success',
                        })
                      }}
                    >
                      Start
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      restartDemoJob(projectId, j.id)
                      pushToast('Job restarted', {
                        description: j.title,
                        kind: 'success',
                      })
                    }}
                  >
                    Restart
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => openEditDemo(j)}>
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      deleteDemoJob(projectId, j.id)
                      pushToast('Job removed', {
                        description: j.title,
                        kind: 'warning',
                      })
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            )
          })
        )}
      </div>

      <CreateResourceModal
        isOpen={open}
        title={editingId ? 'Edit background job' : 'Create background job'}
        submitLabel={editingId ? 'Save' : 'Create'}
        onClose={() => {
          setOpen(false)
          resetForm()
        }}
        onSubmit={() => void submit()}
        isSubmitDisabled={
          submitting ||
          !title.trim() ||
          (useApi && !command.trim()) ||
          (useApi && !sandboxRunning)
        }
      >
        <FormGroup label="Title" isRequired fieldId="job-title">
          <TextInput id="job-title" value={title} onChange={(_e, v) => setTitle(v)} />
        </FormGroup>
        {useApi ? (
          <>
            <FormGroup label="Command" isRequired fieldId="job-command">
              <TextInput
                id="job-command"
                value={command}
                onChange={(_e, v) => setCommand(v)}
                placeholder="npm run dev"
                isDisabled={Boolean(editingRunning)}
              />
            </FormGroup>
            <FormGroup label="Working directory (optional)" fieldId="job-cwd">
              <TextInput
                id="job-cwd"
                value={cwd}
                onChange={(_e, v) => setCwd(v)}
                placeholder="/workspace"
                isDisabled={Boolean(editingRunning)}
              />
            </FormGroup>
            {editingRunning ? (
              <p className="pf-v6-c-helper-text" style={{ marginTop: 8 }}>
                Stop the job to change command or working directory. Title can still be updated.
              </p>
            ) : null}
          </>
        ) : (
          <>
            <FormGroup label="Type" fieldId="job-type">
              <FormSelect id="job-type" value={type} onChange={(_e, v) => setType(v)}>
                <FormSelectOption value="index" label="index" />
                <FormSelectOption value="export" label="export" />
                <FormSelectOption value="workflow_run" label="workflow_run" />
                <FormSelectOption value="custom" label="custom" />
              </FormSelect>
            </FormGroup>
            <FormGroup label="Schedule (optional)" fieldId="job-sched">
              <TextInput
                id="job-sched"
                value={schedule}
                onChange={(_e, v) => setSchedule(v)}
                placeholder="cron or leave empty"
              />
            </FormGroup>
          </>
        )}
      </CreateResourceModal>
    </div>
  )
}
