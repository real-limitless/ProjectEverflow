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
  getJobLogs,
  killJob as killApiJob,
  listJobs,
  type ApiJob,
} from '@/lib/jobsApi'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { JobStatus } from '@/types/studio'
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
  if (status === 'killed' || status === 'cancelled') return 'killed'
  if (status === 'error' || status === 'err') return 'error'
  return status
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

  const [apiJobs, setApiJobs] = useState<ApiJob[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [logsById, setLogsById] = useState<Record<string, string>>({})

  const [open, setOpen] = useState(false)
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
    setTitle('')
    setCommand('npm run dev')
    setCwd('')
    setType('custom')
    setSchedule('')
  }

  const submit = async () => {
    if (!title.trim()) return
    if (useApi) {
      if (!sandboxRunning) {
        pushToast('Sandbox must be running to create a job', { kind: 'warning' })
        return
      }
      if (!command.trim()) return
      setSubmitting(true)
      try {
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
        resetForm()
        setOpen(false)
        setExpandedId(job.id)
      } catch (err) {
        pushToast('Failed to start job', {
          description: err instanceof Error ? err.message : 'Unknown error',
          kind: 'danger',
        })
      } finally {
        setSubmitting(false)
      }
      return
    }

    createDemoJob(projectId, {
      title: title.trim(),
      type,
      schedule: schedule || undefined,
    })
    pushToast('Job created', { description: `${title.trim()} queued`, kind: 'success' })
    resetForm()
    setOpen(false)
  }

  const onKillApi = async (job: ApiJob) => {
    try {
      const updated = await killApiJob(projectId, job.id)
      setApiJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)))
      pushToast('Kill signal sent', {
        description: `Stopped ${job.title}`,
        kind: 'warning',
      })
    } catch (err) {
      pushToast('Failed to kill job', {
        description: err instanceof Error ? err.message : 'Unknown error',
        kind: 'danger',
      })
    }
  }

  const jobs = useApi ? apiJobs : demoJobs
  const canCreate = useApi ? sandboxRunning : true

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          Background jobs
        </span>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setOpen(true)}
          isDisabled={!canCreate}
        >
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
            onPrimary={canCreate ? () => setOpen(true) : undefined}
          />
        ) : useApi ? (
          apiJobs.map((j) => {
            const uiStatus = mapApiStatus(j.status)
            const isExpanded = expandedId === j.id
            const canKill = j.status === 'running'
            return (
              <div className="list-card" key={j.id}>
                <div className="lc-row">
                  <div className="lc-title">{j.title}</div>
                  <StatusLabel status={uiStatus} text={statusLabel(j.status)} />
                </div>
                <div className="lc-meta">
                  <code style={{ fontSize: 12 }}>{j.command}</code>
                  {j.cwd ? ` · ${j.cwd}` : ''}
                  {j.pid != null ? ` · pid ${j.pid}` : ''}
                </div>
                {canKill && (
                  <div style={{ marginTop: 8 }}>
                    <Button variant="secondary" size="sm" onClick={() => void onKillApi(j)}>
                      Kill
                    </Button>
                  </div>
                )}
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
          demoJobs.map((j) => (
            <div className="list-card" key={j.id}>
              <div className="lc-row">
                <div className="lc-title">{j.title}</div>
                <StatusLabel status={j.status} />
              </div>
              <div className="lc-meta">
                {j.type}
                {j.schedule ? ` · ${j.schedule}` : ''} · {j.progress}
              </div>
              {(j.status === 'run' || j.status === 'queued') && (
                <div style={{ marginTop: 8 }}>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      killDemoJob(projectId, j.id)
                      pushToast('Kill signal sent', {
                        description: 'Stop signal sent to the sandbox task.',
                        kind: 'warning',
                      })
                    }}
                  >
                    Kill
                  </Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <CreateResourceModal
        isOpen={open}
        title="Create background job"
        onClose={() => setOpen(false)}
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
              />
            </FormGroup>
            <FormGroup label="Working directory (optional)" fieldId="job-cwd">
              <TextInput
                id="job-cwd"
                value={cwd}
                onChange={(_e, v) => setCwd(v)}
                placeholder="/workspace"
              />
            </FormGroup>
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
