import type { CreateProjectDraft } from '@/data/createProjectDraft'
import type { ProjectTemplateId } from '@/data/projectTemplates'
import type { ProjectRepo } from '@/types/project'
import { getTemplate, reposFromTemplate } from '@/data/projectTemplates'
import { slugifyProjectName } from '@/data/projects'

export type WizardDraft = CreateProjectDraft

export function emptyWizardDraft(): WizardDraft {
  const template = getTemplate('blank')
  return {
    name: '',
    description: '',
    slug: '',
    templateId: 'blank',
    repos: [],
    harnessIds: [...template.defaultHarnessIds],
    options: {
      layout: template.defaultLayout,
      includeSampleData: true,
      environment: 'local',
      visibility: 'private',
      dockPalette: true,
    },
  }
}

export function applyTemplateToDraft(
  draft: WizardDraft,
  templateId: ProjectTemplateId,
): WizardDraft {
  const template = getTemplate(templateId)
  const slug = slugifyProjectName(draft.slug || draft.name || 'project')
  const repos: ProjectRepo[] =
    templateId === 'blank'
      ? draft.repos
      : reposFromTemplate(template, slug)

  return {
    ...draft,
    templateId,
    repos: templateId === 'blank' && !draft.repos.length ? [] : repos,
    harnessIds: [...template.defaultHarnessIds],
    options: {
      ...draft.options,
      layout: template.defaultLayout,
    },
  }
}
