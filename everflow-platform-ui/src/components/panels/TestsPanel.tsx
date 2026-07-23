import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Label,
  TextInput,
} from '@patternfly/react-core'
import { CreateResourceModal } from '@/components/studio/CreateResourceModal'
import { EmptySplash } from '@/components/studio/EmptySplash'
import { getProject } from '@/data/projects'
import {
  createTestCase as createApiTestCase,
  createTestSuite,
  isDemoMode,
  listTestSuites,
  runTestSuite,
} from '@/lib/api'
import { mapApiTestRun, mapApiTestSuite } from '@/lib/studioMap'
import { pushToast } from '@/lib/studioToast'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { useProjectStudio, useStudioDemoStore } from '@/store/studioDemoStore'
import type { TestCaseType } from '@/types/studio'

export function TestsPanel() {
  const projectId = usePlaygroundStore((s) => s.currentProjectId) || 'default'
  const project = getProject(projectId === 'default' ? null : projectId)
  const useApi = Boolean(project?.fromApi) && !isDemoMode()

  const studio = useProjectStudio(projectId)
  const suites = studio.testSuites
  const lastRun = studio.lastTestRun
  const replaceSuites = useStudioDemoStore((s) => s.update)
  const createSuite = useStudioDemoStore((s) => s.createSuite)
  const createTestCase = useStudioDemoStore((s) => s.createTestCase)
  const runSuite = useStudioDemoStore((s) => s.runSuite)

  const [activeSuite, setActiveSuite] = useState(suites[0]?.id ?? '')
  const [suiteOpen, setSuiteOpen] = useState(false)
  const [caseOpen, setCaseOpen] = useState(false)
  const [suiteName, setSuiteName] = useState('')
  const [caseName, setCaseName] = useState('')
  const [caseType, setCaseType] = useState<TestCaseType>('unit')
  const [caseCmd, setCaseCmd] = useState('')
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)

  const refreshApi = useCallback(async () => {
    if (!useApi) return
    setLoading(true)
    try {
      const list = await listTestSuites(projectId)
      const mapped = list.map(mapApiTestSuite)
      replaceSuites(projectId, (s) => ({ ...s, testSuites: mapped }))
      setActiveSuite((prev) => {
        if (prev && mapped.some((x) => x.id === prev)) return prev
        return mapped[0]?.id ?? ''
      })
    } catch (e) {
      pushToast(e instanceof Error ? e.message : 'Failed to load test suites', {
        kind: 'danger',
      })
    } finally {
      setLoading(false)
    }
  }, [projectId, replaceSuites, useApi])

  useEffect(() => {
    void refreshApi()
  }, [refreshApi])

  useEffect(() => {
    if (!useApi) return

    const prev = useStudioDemoStore.getState()
    const prevCreateSuite = prev.createSuite
    const prevCreateCase = prev.createTestCase
    const prevRunSuite = prev.runSuite

    useStudioDemoStore.setState({
      createSuite: (pid, name) => {
        if (pid !== projectId) {
          prevCreateSuite(pid, name)
          return
        }
        prevCreateSuite(pid, name)
        void (async () => {
          try {
            const created = await createTestSuite(pid, { name })
            const mapped = mapApiTestSuite(created)
            useStudioDemoStore.getState().update(pid, (s) => {
              // Replace optimistic local suite (uid prefix) with API row
              let replaced = false
              const next = s.testSuites.map((x) => {
                if (
                  !replaced &&
                  x.name === name &&
                  x.cases.length === 0 &&
                  !/^[0-9a-f-]{36}$/i.test(x.id)
                ) {
                  replaced = true
                  return mapped
                }
                return x
              })
              return {
                ...s,
                testSuites: replaced ? next : [...next.filter((x) => x.id !== mapped.id), mapped],
              }
            })
            setActiveSuite(mapped.id)
          } catch (e) {
            await refreshApi()
            pushToast(e instanceof Error ? e.message : 'Create suite failed', { kind: 'danger' })
          }
        })()
      },
      createTestCase: (pid, suiteId, data) => {
        if (pid !== projectId) {
          prevCreateCase(pid, suiteId, data)
          return
        }
        prevCreateCase(pid, suiteId, data)
        void (async () => {
          try {
            await createApiTestCase(pid, suiteId, {
              name: data.name,
              type: data.type,
              command: data.command,
            })
            await refreshApi()
          } catch (e) {
            await refreshApi()
            pushToast(e instanceof Error ? e.message : 'Create test case failed', {
              kind: 'danger',
            })
          }
        })()
      },
      runSuite: (pid, suiteId) => {
        if (pid !== projectId) {
          prevRunSuite(pid, suiteId)
          return
        }
        void (async () => {
          setRunning(true)
          try {
            const result = await runTestSuite(pid, suiteId)
            await refreshApi()
            useStudioDemoStore.getState().update(pid, (s) => ({
              ...s,
              lastTestRun: mapApiTestRun(result),
            }))
            pushToast('Suite run finished', {
              description: result.summary,
              kind: result.status === 'passed' ? 'success' : 'warning',
            })
          } catch (e) {
            pushToast(e instanceof Error ? e.message : 'Suite run failed', { kind: 'danger' })
          } finally {
            setRunning(false)
          }
        })()
      },
    })

    return () => {
      useStudioDemoStore.setState({
        createSuite: prevCreateSuite,
        createTestCase: prevCreateCase,
        runSuite: prevRunSuite,
      })
    }
  }, [projectId, refreshApi, useApi])

  const suite = suites.find((s) => s.id === activeSuite) ?? suites[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-toolbar">
        <span className="section-label" style={{ margin: 0 }}>
          Tests{useApi && loading ? '…' : ''}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <Button variant="secondary" size="sm" onClick={() => setSuiteOpen(true)}>
            New suite
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setCaseOpen(true)}
            isDisabled={!suite}
          >
            New test
          </Button>
          <Button
            variant="primary"
            size="sm"
            isDisabled={!suite || running}
            isLoading={running}
            onClick={() => {
              if (!suite) return
              runSuite(projectId, suite.id)
              if (!useApi) {
                pushToast('Suite run finished', {
                  description: 'Results updated for this suite.',
                  kind: 'success',
                })
              }
            }}
          >
            Run suite
          </Button>
        </div>
      </div>
      <div className="panel-scroll">
        {lastRun && (
          <div className="list-card">
            <div className="lc-row">
              <div className="lc-title">Latest run</div>
              <Label color={lastRun.failedN ? 'orange' : 'green'}>{lastRun.summary}</Label>
            </div>
          </div>
        )}

        <div className="section-label">Suites</div>
        {suites.length === 0 ? (
          <EmptySplash
            title="No test suites"
            body="Create a suite and add unit, e2e, or smoke cases."
            primaryLabel="New suite"
            onPrimary={() => setSuiteOpen(true)}
          />
        ) : (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
            {suites.map((s) => (
              <Button
                key={s.id}
                size="sm"
                variant={s.id === suite?.id ? 'primary' : 'secondary'}
                onClick={() => setActiveSuite(s.id)}
              >
                {s.name} ({s.cases.length})
              </Button>
            ))}
          </div>
        )}

        {suite && (
          <>
            <div className="section-label">{suite.name} · cases</div>
            {suite.cases.length === 0 ? (
              <EmptySplash
                title="No cases in this suite"
                body="Add a test case with a name and command."
                primaryLabel="New test"
                onPrimary={() => setCaseOpen(true)}
              />
            ) : (
              suite.cases.map((c) => (
                <div className="list-card" key={c.id}>
                  <div className="lc-row">
                    <div className="lc-title">{c.name}</div>
                    <Label
                      color={
                        c.lastStatus === 'failed'
                          ? 'red'
                          : c.lastStatus === 'skipped'
                            ? 'grey'
                            : c.lastStatus === 'passed'
                              ? 'green'
                              : 'grey'
                      }
                    >
                      {c.type} · {c.lastStatus ?? 'pending'}
                    </Label>
                  </div>
                  <div className="lc-meta" style={{ fontFamily: 'var(--mono)' }}>
                    {c.command}
                  </div>
                  {c.error && (
                    <div
                      className="lc-meta"
                      style={{ color: 'var(--pf-t--global--text--color--status--danger--default)' }}
                    >
                      {c.error}
                    </div>
                  )}
                </div>
              ))
            )}
          </>
        )}

        {lastRun && lastRun.failed.length > 0 && (
          <>
            <div className="section-label">Failed (latest)</div>
            {lastRun.failed.map((f) => (
              <div className="list-card" key={f}>
                <div
                  className="lc-title"
                  style={{ color: 'var(--pf-t--global--text--color--status--danger--default)' }}
                >
                  {f}
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      <CreateResourceModal
        isOpen={suiteOpen}
        title="Create test suite"
        onClose={() => setSuiteOpen(false)}
        onSubmit={() => {
          if (!suiteName.trim()) return
          createSuite(projectId, suiteName.trim())
          pushToast('Suite created', { kind: 'success' })
          setSuiteName('')
          setSuiteOpen(false)
        }}
        isSubmitDisabled={!suiteName.trim()}
      >
        <FormGroup label="Suite name" isRequired fieldId="suite-name">
          <TextInput id="suite-name" value={suiteName} onChange={(_e, v) => setSuiteName(v)} />
        </FormGroup>
      </CreateResourceModal>

      <CreateResourceModal
        isOpen={caseOpen}
        title="Create test case"
        onClose={() => setCaseOpen(false)}
        onSubmit={() => {
          if (!suite || !caseName.trim()) return
          createTestCase(projectId, suite.id, {
            name: caseName.trim(),
            type: caseType,
            command: caseCmd || `test ${caseName.trim()}`,
          })
          pushToast('Test case created', { kind: 'success' })
          setCaseName('')
          setCaseCmd('')
          setCaseOpen(false)
        }}
        isSubmitDisabled={!caseName.trim() || !suite}
      >
        <FormGroup label="Name" isRequired fieldId="case-name">
          <TextInput id="case-name" value={caseName} onChange={(_e, v) => setCaseName(v)} />
        </FormGroup>
        <FormGroup label="Type" fieldId="case-type">
          <FormSelect
            id="case-type"
            value={caseType}
            onChange={(_e, v) => setCaseType(v as TestCaseType)}
          >
            <FormSelectOption value="unit" label="unit" />
            <FormSelectOption value="e2e" label="e2e" />
            <FormSelectOption value="smoke" label="smoke" />
          </FormSelect>
        </FormGroup>
        <FormGroup label="Command / assertion" fieldId="case-cmd">
          <TextInput id="case-cmd" value={caseCmd} onChange={(_e, v) => setCaseCmd(v)} />
        </FormGroup>
      </CreateResourceModal>
    </div>
  )
}
