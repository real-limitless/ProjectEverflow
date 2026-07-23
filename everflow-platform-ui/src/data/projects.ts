import { isDemoMode } from '@/lib/api'
import type { ChatMessage } from '@/types/panels'
import type { Project } from '@/types/project'

/** Hardcoded offline-demo catalog entries (Aura Host, Callour Agency, etc.). */
export const SEED_PROJECT_IDS = new Set(['aura', 'callour', 'router'])

export function isSeedProjectId(id: string | null | undefined): boolean {
  return Boolean(id && SEED_PROJECT_IDS.has(id))
}

export const PROJECTS: Record<string, Project> = {
  aura: {
    id: 'aura',
    name: 'Aura Host',
    repos: [
      { id: 'web', label: 'aura-host/web', active: true },
      { id: 'api', label: 'aura-host/api', active: false },
    ],
    convs: [
      { id: 'c1', title: 'Fix MetricCard status ring', meta: 'Active · 2m ago', pinned: true },
      { id: 'c2', title: 'Wire nginx health checks', meta: 'Yesterday' },
      { id: 'c3', title: 'Deploy postgres-db scaling', meta: '3 days ago' },
    ],
    messages: [
      {
        id: 'm1',
        role: 'user',
        text: "The MetricCard status ring doesn't map Warning correctly when memory hits 67%. Can you fix it?",
      },
      {
        id: 'm2',
        role: 'assistant',
        thinking: 'Finished thinking — MetricCard maps percentage → Healthy/Warning/Critical.',
        text: 'Updated thresholds: ≥65% → warning, ≥90% → critical. Diff is in Repository → Changes.',
        tool: {
          title: 'sandbox_str_replace · MetricCard.tsx',
          body: `-  const status = pct < 80 ? "healthy" : "critical";\n+  const status =\n+    pct >= 90 ? "critical" :\n+    pct >= 65 ? "warning" : "healthy";`,
        },
      },
    ],
    files: [
      { path: 'src/pages/Index.tsx', name: 'Index.tsx', folder: 'pages' },
      {
        path: 'src/components/dashboard/MetricCard.tsx',
        name: 'MetricCard.tsx',
        folder: 'dashboard',
      },
      { path: 'src/App.tsx', name: 'App.tsx', folder: 'src' },
      { path: 'src/styles/theme.css', name: 'theme.css', folder: 'styles' },
      { path: 'docs/architecture.md', name: 'architecture.md', folder: 'docs' },
      { path: 'docs/runbook.md', name: 'runbook.md', folder: 'docs' },
      { path: 'package.json', name: 'package.json', folder: '' },
    ],
    code: {
      'Index.tsx': `<span class="tok-kw">import</span> { MetricCard } <span class="tok-kw">from</span> <span class="tok-str">"@/components/dashboard/MetricCard"</span>;\n\n<span class="tok-kw">const</span> Index = () =&gt; (\n  &lt;<span class="tok-tag">main</span> <span class="tok-attr">className</span>=<span class="tok-str">"p-6"</span>&gt;\n    &lt;<span class="tok-tag">MetricCard</span> <span class="tok-attr">title</span>=<span class="tok-str">"CPU Usage"</span> <span class="tok-attr">percentage</span>={42} /&gt;\n  &lt;/<span class="tok-tag">main</span>&gt;\n);`,
      'MetricCard.tsx': `<span class="tok-kw">export function</span> <span class="tok-fn">MetricCard</span>({ title, percentage, status }) {\n  <span class="tok-kw">const</span> ring =\n    status === <span class="tok-str">"critical"</span> ? <span class="tok-str">"danger"</span> :\n    status === <span class="tok-str">"warning"</span> ? <span class="tok-str">"warn"</span> : <span class="tok-str">"ok"</span>;\n  // TODO: animate ring transitions\n  console.log("metric", percentage);\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">div</span> <span class="tok-attr">className</span>={ring}&gt;{title}: {percentage}%&lt;/<span class="tok-tag">div</span>&gt;;\n}`,
      'App.tsx': `<span class="tok-kw">export default function</span> <span class="tok-fn">App</span>() {\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">RouterProvider</span> /&gt;;\n}`,
      'theme.css': `:root {\n  --ring-ok: #16a34a;\n  --ring-warn: #ca8a04;\n  --ring-danger: #dc2626;\n}\n\n.metric-card {\n  border-radius: 0.5rem;\n  padding: 1rem;\n}`,
      'architecture.md': `## Aura Host architecture\n\n- Web UI (Vite + React)\n- API gateway\n- Postgres for metrics history`,
      'runbook.md': `## Runbook\n\n1. Check MetricCard thresholds\n2. Verify nginx health probes\n3. Scale postgres if p99 &gt; 200ms`,
      'package.json': `{\n  "name": "aura-host-web",\n  "private": true,\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc -b && vite build"\n  }\n}`,
    },
    gitChanges: [
      {
        path: 'src/components/dashboard/MetricCard.tsx',
        status: 'M',
        additions: 4,
        deletions: 1,
        label: 'MetricCard.tsx',
        diffPreview:
          '@@ -12,3 +12,6 @@\n- const status = pct < 80 ? "healthy" : "critical";\n+ const status =\n+   pct >= 90 ? "critical" :\n+   pct >= 65 ? "warning" : "healthy";',
      },
      {
        path: 'docs/runbook.md',
        status: 'A',
        additions: 12,
        deletions: 0,
        label: 'runbook.md',
      },
      {
        path: 'src/legacy/StatusBadge.tsx',
        status: 'D',
        additions: 0,
        deletions: 28,
        label: 'StatusBadge.tsx',
      },
      {
        path: 'src/styles/theme.css',
        status: 'M',
        additions: 6,
        deletions: 2,
        label: 'theme.css',
      },
    ],
    knowledgeFiles: [
      { name: 'architecture.md', path: 'docs/architecture.md' },
      { name: 'runbook.md', path: 'docs/runbook.md' },
    ],
    canvases: [
      { name: 'MetricCard redesign', desc: 'Status ring thresholds' },
      { name: 'Deploy checklist', desc: 'Staging → prod' },
    ],
    termLines: [
      { cls: 'muted', text: 'sandbox@aura-host-web:~$' },
      { cls: 'cmd', text: ' npm run dev' },
      { cls: '', text: '  VITE v5.4.0  ready in 312 ms' },
      { cls: '', text: '  ➜  Local:   http://localhost:5173/' },
      { cls: 'muted', text: 'sandbox@aura-host-web:~$' },
    ],
  },
  callour: {
    id: 'callour',
    name: 'Callour Agency',
    repos: [{ id: 'site', label: 'callour/site', active: true }],
    convs: [
      { id: 'c1', title: 'Hero photo + brand colors', meta: 'Active · 1h ago' },
      { id: 'c2', title: 'Client logo strip', meta: '2 days ago' },
    ],
    messages: [
      {
        id: 'call_m1',
        role: 'user',
        text: 'Make the landing hero match the team photo on red background.',
      },
      {
        id: 'call_m2',
        role: 'assistant',
        thinking: 'Drafting hero layout from design reference…',
        text: 'Hero updated with team photo, Callour mark, and Plus Jakarta Sans. Check Preview.',
        tool: {
          title: 'sandbox_write_file · index.html',
          body: `+ <h1>Creative Design and Development Agency</h1>`,
        },
      },
    ],
    files: [
      { path: 'index.html', name: 'index.html', folder: 'root' },
      { path: 'styles.css', name: 'styles.css', folder: 'root' },
      { path: 'assets/logo.svg', name: 'logo.svg', folder: 'assets' },
    ],
    code: {
      'index.html': `<span class="tok-com">&lt;!DOCTYPE html&gt;</span>\n&lt;<span class="tok-tag">html</span>&gt;\n  &lt;<span class="tok-tag">h1</span>&gt;Creative Design and Development Agency&lt;/<span class="tok-tag">h1</span>&gt;\n&lt;/<span class="tok-tag">html</span>&gt;`,
      'styles.css': `<span class="tok-tag">:root</span> { --red: <span class="tok-str">#c62828</span>; }\n<span class="tok-tag">body</span> { font-family: <span class="tok-str">'Plus Jakarta Sans'</span>, sans-serif; }`,
      'logo.svg': `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n  <circle cx="16" cy="16" r="12" fill="#c62828"/>\n</svg>`,
    },
    gitChanges: [
      {
        path: 'index.html',
        status: 'M',
        additions: 3,
        deletions: 1,
      },
      {
        path: 'assets/logo.svg',
        status: 'A',
        additions: 4,
        deletions: 0,
      },
    ],
    knowledgeFiles: [{ name: 'brand-guide.md', path: 'docs/brand-guide.md' }],
    canvases: [{ name: 'Landing copy', desc: 'Hero + services' }],
    termLines: [
      { cls: 'muted', text: 'sandbox@callour-site:~$' },
      { cls: 'cmd', text: ' python -m http.server 8080' },
      { cls: '', text: 'Serving HTTP on 0.0.0.0 port 8080 …' },
    ],
  },
  router: {
    id: 'router',
    name: 'ProjectEverflow Core',
    repos: [
      { id: 'fe', label: 'projecteverflow-repo2', active: true },
      { id: 'be', label: 'projecteverflow', active: false },
      { id: 'docs', label: 'projecteverflow-core', active: false },
    ],
    convs: [
      { id: 'c1', title: 'Playground v2 shell', meta: 'Active · now' },
      { id: 'c2', title: 'Studio chat resizable split', meta: 'Last week' },
    ],
    messages: [
      {
        id: 'r_m1',
        role: 'user',
        text: 'Add VS Code-style docking for Playground v2.',
      },
      {
        id: 'r_m2',
        role: 'assistant',
        text: 'Layout tree supports horizontal/vertical splits, stackable tabs, detach-to-window, and project tabs.',
        tool: {
          title: 'plan · playground-v2.html',
          body: `+ dock tree (split | group)\n+ drag tabs → edges / center\n+ detach window\n+ project tab bar`,
        },
      },
    ],
    files: [
      { path: 'demos/playground-v2.html', name: 'playground-v2.html', folder: 'demos' },
      { path: 'docs/TECH.md', name: 'TECH.md', folder: 'docs' },
      { path: 'everflow-platform-ui/src/components/panels/CodePanel.tsx', name: 'CodePanel.tsx', folder: 'panels' },
    ],
    code: {
      'playground-v2.html': `<span class="tok-com">&lt;!-- dockable playground v2 --&gt;</span>\n&lt;<span class="tok-tag">div</span> <span class="tok-attr">class</span>=<span class="tok-str">"dock-root"</span>&gt;…&lt;/<span class="tok-tag">div</span>&gt;`,
      'TECH.md': `<span class="tok-com">## Playground v2</span>\nProject-first + dockable workbench.`,
      'CodePanel.tsx': `export function CodePanel({ panelKey }) {\n  // nested tree + multi-tabs + git gutters\n  return null;\n}`,
    },
    gitChanges: [
      {
        path: 'everflow-platform-ui/src/components/panels/CodePanel.tsx',
        status: 'M',
        additions: 180,
        deletions: 40,
      },
      {
        path: 'demos/playground-v2.html',
        status: 'M',
        additions: 12,
        deletions: 5,
      },
    ],
    knowledgeFiles: [
      { name: 'HANDOFF.md', path: 'HANDOFF.md' },
      { name: 'IMPLEMENTATION.md', path: 'IMPLEMENTATION.md' },
    ],
    canvases: [{ name: 'v2 layout wireframe', desc: 'Dock tree' }],
    termLines: [
      { cls: 'muted', text: 'sandbox@projecteverflow:~$' },
      { cls: 'cmd', text: ' ./scripts/local-stack.sh status' },
      { cls: '', text: 'frontend  up  :3000\nbackend   up  :8000' },
    ],
  },
}

export function listProjectIds(): string[] {
  return Object.keys(PROJECTS)
}

/**
 * Project ids safe to show in non-demo UI (excludes pure seed demos).
 * Demo mode still returns the full catalog.
 */
export function listVisibleProjectIds(): string[] {
  if (isDemoMode()) return listProjectIds()
  return listProjectIds().filter((id) => {
    const p = PROJECTS[id]
    if (!p) return false
    // Hide offline demo seeds; keep user-created and API projects
    if (isSeedProjectId(id) && !p.fromApi) return false
    return true
  })
}

/** @deprecated use listProjectIds() — kept as live getter for existing imports */
export const PROJECT_IDS = listProjectIds()

export function getProject(id: string | null | undefined): Project | undefined {
  if (!id) return undefined
  return PROJECTS[id]
}

export function addProjectToCatalog(project: Project): void {
  PROJECTS[project.id] = project
}

/** Patch an existing catalog project (in-memory; persist via store for user projects). */
export function updateProjectInCatalog(
  id: string,
  patch: Partial<Project>,
): Project | null {
  const existing = PROJECTS[id]
  if (!existing) return null
  const next: Project = {
    ...existing,
    ...patch,
    id: existing.id,
  }
  PROJECTS[id] = next
  return next
}

/** Restore user-created projects from persistence (does not overwrite seeds). */
export function mergeUserProjects(
  userProjects: Record<string, Project> | undefined | null,
): void {
  if (!userProjects) return
  for (const [id, p] of Object.entries(userProjects)) {
    if (!p?.id || !p?.name) continue
    if (!PROJECTS[id]) PROJECTS[id] = p
  }
}

export function listUserCreatedProjects(
  seedIds: Set<string> = SEED_PROJECT_IDS,
): Record<string, Project> {
  const out: Record<string, Project> = {}
  for (const [id, p] of Object.entries(PROJECTS)) {
    if (!seedIds.has(id)) out[id] = p
  }
  return out
}

export function slugifyProjectName(name: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32)
  return base || 'project'
}

export function createBlankProject(name: string, id?: string): Project {
  const trimmed = name.trim() || 'Untitled project'
  const slug = slugifyProjectName(trimmed)
  const projectId =
    id || `${slug}-${Math.random().toString(36).slice(2, 6)}`
  return {
    id: projectId,
    name: trimmed,
    slug,
    templateId: 'blank',
    description: '',
    repos: [{ id: 'main', label: `${slug}/app`, active: true, branch: 'main' }],
    harnesses: [
      { id: 'agent-claude-code', label: 'Claude Code', enabled: true },
      { id: 'agent-opencode', label: 'OpenCode', enabled: true },
    ],
    layoutMode: 'standard',
    environment: 'local',
    visibility: 'private',
    convs: [
      {
        id: 'c1',
        title: 'Getting started',
        meta: 'Just now',
      },
    ],
    messages: [] as ChatMessage[],
    files: [
      { path: 'README.md', name: 'README.md', folder: '' },
      { path: 'src/App.tsx', name: 'App.tsx', folder: 'src' },
    ],
    code: {
      'README.md': `# ${trimmed}\n\nNew Everflow project.`,
      'App.tsx': `<span class="tok-kw">export default function</span> <span class="tok-fn">App</span>() {\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">div</span>&gt;Hello ${trimmed}&lt;/<span class="tok-tag">div</span>&gt;;\n}`,
    },
    knowledgeFiles: [],
    canvases: [],
    termLines: [
      { cls: 'muted', text: `sandbox@${slug}:~$` },
      { cls: 'cmd', text: ' echo "Project ready"' },
      { cls: '', text: 'Project ready' },
    ],
  }
}


