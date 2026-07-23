import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Form,
  FormGroup,
  FormHelperText,
  FormSection,
  FormSelect,
  FormSelectOption,
  Grid,
  GridItem,
  HelperText,
  HelperTextItem,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalVariant,
  Tab,
  Tabs,
  TabTitleText,
  TextArea,
  TextInput,
} from '@patternfly/react-core'
import { enabledHarnessIds, harnessesFromIds } from '@/data/harnesses'
import { getProject } from '@/data/projects'
import { ProvidersManager } from '@/components/providers/ProvidersManager'
import { HarnessPicker } from '@/components/project-settings/HarnessPicker'
import { usePlaygroundStore } from '@/store/playgroundStore'
import type {
  ProjectEnvironment,
  ProjectVisibility,
  WorkspaceLayoutMode,
} from '@/types/project'

type SettingsTab = 'general' | 'harnesses' | 'providers' | 'workbench'

interface SettingsDraft {
  name: string
  description: string
  environment: ProjectEnvironment
  visibility: ProjectVisibility
  layoutMode: WorkspaceLayoutMode
  harnessIds: string[]
}

function draftFromProject(projectId: string): SettingsDraft | null {
  const p = getProject(projectId)
  if (!p) return null
  return {
    name: p.name,
    description: p.description || '',
    environment: p.environment || 'local',
    visibility: p.visibility || 'private',
    layoutMode: p.layoutMode || 'standard',
    harnessIds: enabledHarnessIds(p.harnesses),
  }
}

export function ProjectSettingsModal() {
  const isOpen = usePlaygroundStore((s) => s.projectSettingsOpen)
  const projectId = usePlaygroundStore((s) => s.projectSettingsProjectId)
  const close = usePlaygroundStore((s) => s.closeProjectSettings)
  const updateProject = usePlaygroundStore((s) => s.updateProject)

  const [tab, setTab] = useState<SettingsTab>('general')
  const [draft, setDraft] = useState<SettingsDraft | null>(null)
  const [error, setError] = useState('')

  // Reset draft whenever the modal opens or target project changes
  useEffect(() => {
    if (!isOpen || !projectId) {
      setDraft(null)
      setError('')
      setTab('general')
      return
    }
    setDraft(draftFromProject(projectId))
    setError('')
    setTab('general')
  }, [isOpen, projectId])

  const project = projectId ? getProject(projectId) : undefined
  const title = useMemo(
    () => (project ? `Project settings · ${project.name}` : 'Project settings'),
    [project],
  )

  const patch = (p: Partial<SettingsDraft>) => {
    setDraft((d) => (d ? { ...d, ...p } : d))
    if (error) setError('')
  }

  const onSave = () => {
    if (!projectId || !draft) return
    const name = draft.name.trim()
    if (!name) {
      setError('Project name is required.')
      setTab('general')
      return
    }
    const ok = updateProject(projectId, {
      name,
      description: draft.description.trim(),
      environment: draft.environment,
      visibility: draft.visibility,
      layoutMode: draft.layoutMode,
      harnesses: harnessesFromIds(draft.harnessIds),
    })
    if (!ok) {
      setError('Could not update project.')
      return
    }
    close()
  }

  return (
    <Modal
      variant={ModalVariant.medium}
      isOpen={isOpen && Boolean(projectId && draft)}
      onClose={close}
      aria-labelledby="project-settings-title"
      className="project-settings-modal"
    >
      <ModalHeader title={title} labelId="project-settings-title" />
      <ModalBody>
        {draft && project ? (
          <>
            <Tabs
              activeKey={tab}
              onSelect={(_e, k) => setTab(k as SettingsTab)}
              className="project-settings-tabs"
            >
              <Tab eventKey="general" title={<TabTitleText>General</TabTitleText>} />
              <Tab eventKey="harnesses" title={<TabTitleText>Harnesses</TabTitleText>} />
              <Tab eventKey="providers" title={<TabTitleText>Providers</TabTitleText>} />
              <Tab eventKey="workbench" title={<TabTitleText>Workbench</TabTitleText>} />
            </Tabs>

            <div className="project-settings-body">
              {error ? (
                <Alert
                  variant="danger"
                  isInline
                  isPlain
                  title={error}
                  className="project-settings-alert"
                  role="alert"
                />
              ) : null}

              {tab === 'general' && (
                <Form className="project-settings-form">
                  <FormSection title="Identity" titleElement="h2">
                    <Grid hasGutter md={6}>
                      <GridItem span={12} md={6}>
                        <FormGroup label="Name" fieldId="ps-name" isRequired>
                          <TextInput
                            id="ps-name"
                            value={draft.name}
                            onChange={(_e, v) => patch({ name: v })}
                            aria-label="Project name"
                            isRequired
                            validated={error && !draft.name.trim() ? 'error' : 'default'}
                          />
                        </FormGroup>
                      </GridItem>
                      <GridItem span={12} md={6}>
                        <FormGroup label="Slug" fieldId="ps-slug">
                          <TextInput
                            id="ps-slug"
                            value={project.slug || project.id}
                            readOnlyVariant="default"
                            aria-label="Project slug"
                          />
                          <FormHelperText>
                            <HelperText>
                              <HelperTextItem>
                                Used in URLs and sandbox paths. Cannot be changed after create.
                              </HelperTextItem>
                            </HelperText>
                          </FormHelperText>
                        </FormGroup>
                      </GridItem>
                      <GridItem span={12}>
                        <FormGroup label="Description" fieldId="ps-desc">
                          <TextArea
                            id="ps-desc"
                            value={draft.description}
                            onChange={(_e, v) => patch({ description: v })}
                            aria-label="Project description"
                            rows={3}
                            resizeOrientation="vertical"
                          />
                          <FormHelperText>
                            <HelperText>
                              <HelperTextItem>
                                Optional summary shown in project lists and the open dialog.
                              </HelperTextItem>
                            </HelperText>
                          </FormHelperText>
                        </FormGroup>
                      </GridItem>
                    </Grid>
                  </FormSection>

                  <FormSection title="Access" titleElement="h2">
                    <Grid hasGutter md={6}>
                      <GridItem span={12} md={6}>
                        <FormGroup label="Environment" fieldId="ps-env">
                          <FormSelect
                            id="ps-env"
                            value={draft.environment}
                            onChange={(_e, v) =>
                              patch({ environment: v as ProjectEnvironment })
                            }
                            aria-label="Environment"
                          >
                            <FormSelectOption value="local" label="Local" />
                            <FormSelectOption value="staging" label="Staging" />
                            <FormSelectOption
                              value="production-stub"
                              label="Production (stub)"
                            />
                          </FormSelect>
                          <FormHelperText>
                            <HelperText>
                              <HelperTextItem>
                                Target environment for this project’s workbench defaults.
                              </HelperTextItem>
                            </HelperText>
                          </FormHelperText>
                        </FormGroup>
                      </GridItem>
                      <GridItem span={12} md={6}>
                        <FormGroup label="Visibility" fieldId="ps-vis">
                          <FormSelect
                            id="ps-vis"
                            value={draft.visibility}
                            onChange={(_e, v) =>
                              patch({ visibility: v as ProjectVisibility })
                            }
                            aria-label="Visibility"
                          >
                            <FormSelectOption
                              value="private"
                              label="Private (organization)"
                            />
                            <FormSelectOption value="public" label="Public" />
                          </FormSelect>
                          <FormHelperText>
                            <HelperText>
                              <HelperTextItem>
                                Who can discover and open this project.
                              </HelperTextItem>
                            </HelperText>
                          </FormHelperText>
                        </FormGroup>
                      </GridItem>
                    </Grid>
                  </FormSection>
                </Form>
              )}

              {tab === 'harnesses' && (
                <HarnessPicker
                  idPrefix="ps-harness"
                  selectedIds={draft.harnessIds}
                  onChange={(harnessIds) => patch({ harnessIds })}
                  lead={
                    <>
                      Enable the harnesses this project should use. Changes apply when you
                      save — they are not limited to what you chose at create time.
                    </>
                  }
                />
              )}

              {tab === 'providers' && (
                <ProvidersManager
                  scope="project"
                  projectId={projectId || undefined}
                  lead={
                    <>
                      Optional project overrides. These keys take priority over your account
                      AI providers for this project’s chat, embeddings, and OCR. Changes save
                      immediately (independent of the footer Save button).
                    </>
                  }
                />
              )}

              {tab === 'workbench' && (
                <Form className="project-settings-form">
                  <FormSection title="Workbench defaults" titleElement="h2">
                    <p className="project-settings-lead">
                      Defaults for how this project opens in the workbench. Existing open
                      layouts are not reset automatically.
                    </p>
                    <FormGroup label="Default workspace layout" fieldId="ps-layout">
                      <FormSelect
                        id="ps-layout"
                        value={draft.layoutMode}
                        onChange={(_e, v) =>
                          patch({ layoutMode: v as WorkspaceLayoutMode })
                        }
                        aria-label="Workspace layout"
                      >
                        <FormSelectOption
                          value="standard"
                          label="Standard (chat + preview stack)"
                        />
                        <FormSelectOption value="chat-first" label="Chat-first" />
                        <FormSelectOption value="code-first" label="Code-first" />
                      </FormSelect>
                      <FormHelperText>
                        <HelperText>
                          <HelperTextItem>
                            Applied when the project is opened with no saved layout.
                          </HelperTextItem>
                        </HelperText>
                      </FormHelperText>
                    </FormGroup>
                  </FormSection>
                </Form>
              )}
            </div>
          </>
        ) : null}
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" onClick={onSave} isDisabled={!draft}>
          Save
        </Button>
        <Button variant="link" onClick={close}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
