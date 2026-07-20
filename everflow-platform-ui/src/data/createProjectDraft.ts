import type { ChatMessage } from '@/types/panels'
import type {
  Project,
  ProjectEnvironment,
  ProjectRepo,
  ProjectVisibility,
  WorkspaceLayoutMode,
} from '@/types/project'
import { DEFAULT_AGENT_HARNESS_IDS, harnessesFromIds } from './harnesses'
import { getTemplate, type ProjectTemplateId } from './projectTemplates'
import { PROJECTS, slugifyProjectName } from './projects'
import type { ApiProject } from '@/lib/api'

export interface CreateProjectDraft {
  name: string
  description?: string
  slug?: string
  templateId: ProjectTemplateId
  repos: ProjectRepo[]
  harnessIds: string[]
  options: {
    layout: WorkspaceLayoutMode
    includeSampleData: boolean
    environment: ProjectEnvironment
    visibility: ProjectVisibility
    dockPalette: boolean
  }
}

export function isSlugTaken(slug: string, excludeId?: string): boolean {
  const s = slug.trim().toLowerCase()
  if (!s) return false
  return Object.values(PROJECTS).some(
    (p) => p.id !== excludeId && (p.slug === s || p.id === s),
  )
}

export function createProjectFromDraft(
  draft: CreateProjectDraft,
  opts?: { apiProject?: ApiProject },
): Project {
  const trimmed = draft.name.trim() || 'Untitled project'
  const baseSlug =
    opts?.apiProject?.slug || slugifyProjectName(draft.slug?.trim() || trimmed)
  let projectId = opts?.apiProject?.id || baseSlug
  if (!opts?.apiProject && PROJECTS[projectId]) {
    projectId = `${baseSlug}-${Math.random().toString(36).slice(2, 6)}`
  }

  const harnessIds =
    draft.harnessIds.length > 0
      ? draft.harnessIds
      : [...DEFAULT_AGENT_HARNESS_IDS]

  const template = getTemplate(draft.templateId)
  const repos =
    draft.repos.length > 0
      ? draft.repos.map((r, i) => ({
          ...r,
          id: r.id || `repo-${i}`,
          active: i === 0 ? true : !!r.active && i === 0 ? true : r.active,
        }))
      : [
          {
            id: 'main',
            label: `${baseSlug}/app`,
            active: true,
            branch: 'main',
            provider: 'none' as const,
          },
        ]

  // Ensure exactly one active repo
  let sawActive = false
  const normalizedRepos = repos.map((r) => {
    if (r.active && !sawActive) {
      sawActive = true
      return { ...r, active: true }
    }
    return { ...r, active: false }
  })
  if (!sawActive && normalizedRepos[0]) normalizedRepos[0].active = true

  const harnesses = harnessesFromIds(harnessIds)
  const includeSample = draft.options.includeSampleData

  let files = [
    { path: 'README.md', name: 'README.md', folder: '' },
    { path: 'src/App.tsx', name: 'App.tsx', folder: 'src' },
  ]
  let code: Record<string, string> = {
    'README.md': `# ${trimmed}\n\n${draft.description?.trim() || 'New Everflow project.'}`,
    'App.tsx': `<span class="tok-kw">export default function</span> <span class="tok-fn">App</span>() {\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">div</span>&gt;Hello ${trimmed}&lt;/<span class="tok-tag">div</span>&gt;;\n}`,
  }

  if (template.seedFiles?.length) {
    files = template.seedFiles.map((f) => ({
      path: f.path,
      name: f.name,
      folder: f.folder,
    }))
    code = {}
    for (const f of template.seedFiles) {
      code[f.name] = f.content.replace(/\$\{name\}/g, trimmed)
      if (f.name === 'README.md') {
        code[f.name] =
          `# ${trimmed}\n\n${draft.description?.trim() || f.content.split('\n').slice(2).join('\n') || 'New Everflow project.'}`
      }
    }
  }

  if (!includeSample) {
    // Minimal: keep README only when blank-ish
    if (template.id === 'blank') {
      files = [{ path: 'README.md', name: 'README.md', folder: '' }]
      code = {
        'README.md': `# ${trimmed}\n\n${draft.description?.trim() || 'Empty project scaffold.'}`,
      }
    }
  }

  return {
    id: projectId,
    name: opts?.apiProject?.name || trimmed,
    description:
      opts?.apiProject?.description ?? (draft.description?.trim() || ''),
    slug: baseSlug,
    templateId: template.id,
    layoutMode: draft.options.layout || template.defaultLayout,
    environment: draft.options.environment,
    visibility: draft.options.visibility,
    fromApi: Boolean(opts?.apiProject),
    organizationId: opts?.apiProject?.organization_id,
    sandboxName: opts?.apiProject?.sandbox_name,
    sandboxStatus: opts?.apiProject?.sandbox_status ?? (opts?.apiProject ? 'pending' : undefined),
    sandboxImage: opts?.apiProject?.sandbox_image,
    sandboxError: opts?.apiProject?.sandbox_error,
    sandboxCreatedAt: opts?.apiProject?.sandbox_created_at,
    repos: normalizedRepos,
    harnesses,
    convs: includeSample
      ? [{ id: 'c1', title: 'Getting started', meta: 'Just now' }]
      : [{ id: 'c1', title: 'New chat', meta: 'Just now' }],
    messages: [] as ChatMessage[],
    files,
    code,
    knowledgeFiles: includeSample
      ? [{ name: 'getting-started.md', path: 'docs/getting-started.md' }]
      : [],
    canvases: includeSample ? [{ name: 'Kickoff', desc: 'First canvas' }] : [],
    termLines: [
      { cls: 'muted', text: `sandbox@${baseSlug}:~$` },
      { cls: 'cmd', text: ' echo "Project ready"' },
      {
        cls: '',
        text: `Project ready · template=${template.id} · harnesses=${harnesses.length}`,
      },
    ],
  }
}
