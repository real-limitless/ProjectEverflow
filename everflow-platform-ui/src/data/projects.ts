import type { Project } from '@/types/project'

export const PROJECTS: Record<string, Project> = {
  aura: {
    id: 'aura',
    name: 'Aura Host',
    repos: [
      { id: 'web', label: 'aura-host/web', active: true },
      { id: 'api', label: 'aura-host/api', active: false },
    ],
    convs: [
      { id: 'c1', title: 'Fix MetricCard status ring', meta: 'Active · 2m ago' },
      { id: 'c2', title: 'Wire nginx health checks', meta: 'Yesterday' },
      { id: 'c3', title: 'Deploy postgres-db scaling', meta: '3 days ago' },
    ],
    messages: [
      {
        role: 'user',
        text: "The MetricCard status ring doesn't map Warning correctly when memory hits 67%. Can you fix it?",
      },
      {
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
    ],
    code: {
      'Index.tsx': `<span class="tok-kw">import</span> { MetricCard } <span class="tok-kw">from</span> <span class="tok-str">"@/components/dashboard/MetricCard"</span>;\n\n<span class="tok-kw">const</span> Index = () =&gt; (\n  &lt;<span class="tok-tag">main</span> <span class="tok-attr">className</span>=<span class="tok-str">"p-6"</span>&gt;\n    &lt;<span class="tok-tag">MetricCard</span> <span class="tok-attr">title</span>=<span class="tok-str">"CPU Usage"</span> <span class="tok-attr">percentage</span>={42} /&gt;\n  &lt;/<span class="tok-tag">main</span>&gt;\n);`,
      'MetricCard.tsx': `<span class="tok-kw">export function</span> <span class="tok-fn">MetricCard</span>({ title, percentage, status }) {\n  <span class="tok-kw">const</span> ring =\n    status === <span class="tok-str">"critical"</span> ? <span class="tok-str">"danger"</span> :\n    status === <span class="tok-str">"warning"</span> ? <span class="tok-str">"warn"</span> : <span class="tok-str">"ok"</span>;\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">div</span> <span class="tok-attr">className</span>={ring}&gt;{title}: {percentage}%&lt;/<span class="tok-tag">div</span>&gt;;\n}`,
      'App.tsx': `<span class="tok-kw">export default function</span> <span class="tok-fn">App</span>() {\n  <span class="tok-kw">return</span> &lt;<span class="tok-tag">RouterProvider</span> /&gt;;\n}`,
    },
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
        role: 'user',
        text: 'Make the landing hero match the team photo on red background.',
      },
      {
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
    ],
    code: {
      'index.html': `<span class="tok-com">&lt;!DOCTYPE html&gt;</span>\n&lt;<span class="tok-tag">html</span>&gt;\n  &lt;<span class="tok-tag">h1</span>&gt;Creative Design and Development Agency&lt;/<span class="tok-tag">h1</span>&gt;\n&lt;/<span class="tok-tag">html</span>&gt;`,
      'styles.css': `<span class="tok-tag">:root</span> { --red: <span class="tok-str">#c62828</span>; }\n<span class="tok-tag">body</span> { font-family: <span class="tok-str">'Plus Jakarta Sans'</span>, sans-serif; }`,
    },
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
        role: 'user',
        text: 'Add VS Code-style docking for Playground v2.',
      },
      {
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
      { path: 'TECH.md', name: 'TECH.md', folder: 'docs' },
    ],
    code: {
      'playground-v2.html': `<span class="tok-com">&lt;!-- dockable playground v2 --&gt;</span>\n&lt;<span class="tok-tag">div</span> <span class="tok-attr">class</span>=<span class="tok-str">"dock-root"</span>&gt;…&lt;/<span class="tok-tag">div</span>&gt;`,
      'TECH.md': `<span class="tok-com">## Playground v2</span>\nProject-first + dockable workbench.`,
    },
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

export const PROJECT_IDS = Object.keys(PROJECTS)
