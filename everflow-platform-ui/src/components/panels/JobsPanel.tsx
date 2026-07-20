import { useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import { StatusLabel } from './statusLabel'

export function JobsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const jobs = useProjectStudio(projectId).jobs
  const createJob = useStudioDemoStore((s) => s.createJob)
  const killJob = useStudioDemoStore((s) => s.killJob)

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [type, setType] = useState('custom')
  const [schedule, setSchedule] = useState('')

  const submit = () => {
    if (!title.trim()) return
    createJob(projectId, { title: title.trim(), type, schedule: schedule || undefined })
    pushToast('Job created', { description: `${title} queued (demo)`, kind: 'success' })
    setTitle('')
    setSchedule('')
    setType('custom')
    setOpen(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          Background jobs
        </span>
        <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
          Create job
        </Button>
      </div>
      <div className="panel-scroll">
        {jobs.length === 0 ? (
          <EmptySplash
            title="No background jobs"
            body="Create a job to index, export, or run work in the sandbox (demo queue)."
            primaryLabel="Create job"
            onPrimary={() => setOpen(true)}
          />
        ) : (
          jobs.map((j) => (
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
                      killJob(projectId, j.id)
                      pushToast('Kill signal sent', {
                        description: 'Would signal sandbox task (demo — not wired)',
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
        onSubmit={submit}
        isSubmitDisabled={!title.trim()}
      >
        <FormGroup label="Title" isRequired fieldId="job-title">
          <TextInput id="job-title" value={title} onChange={(_e, v) => setTitle(v)} />
        </FormGroup>
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
      </CreateResourceModal>
    </div>
  )
}
