import type {
  ProjectRepo,
  WorkspaceLayoutMode,
} from '@/types/project'

export type ProjectTemplateId =
  | 'blank'
  | 'web-npm'
  | 'web-php'
  | 'mobile-ios'
  | 'mobile-android'
  | 'desktop-gui'
  | 'python-api'
  | 'fullstack'

export interface ProjectTemplate {
  id: ProjectTemplateId
  name: string
  description: string
  icon: string
  defaultRepos: Omit<ProjectRepo, 'active'>[]
  defaultHarnessIds: string[]
  defaultLayout: WorkspaceLayoutMode
  /** Optional starter files (name → path + content) */
  seedFiles?: { path: string; name: string; folder: string; content: string }[]
}

export const PROJECT_TEMPLATES: ProjectTemplate[] = [
  {
    id: 'blank',
    name: 'Blank project',
    description: 'Empty scaffold — add repos and harnesses yourself.',
    icon: '◇',
    defaultRepos: [],
    defaultHarnessIds: ['agent-claude-code', 'agent-opencode'],
    defaultLayout: 'standard',
  },
  {
    id: 'web-npm',
    name: 'Web app (npm / Node)',
    description: 'Vite + React style frontend with package.json and Preview.',
    icon: '⬢',
    defaultRepos: [
      {
        id: 'web',
        label: 'app/web',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'preview-env', 'ai-sandbox', 'test-runner'],
    defaultLayout: 'standard',
    seedFiles: [
      {
        path: 'package.json',
        name: 'package.json',
        folder: '',
        content: `{\n  "name": "app",\n  "private": true,\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build",\n    "test": "vitest"\n  }\n}`,
      },
      {
        path: 'src/App.tsx',
        name: 'App.tsx',
        folder: 'src',
        content: `export default function App() {\n  return <main>Hello from npm web app</main>\n}`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# Web app (npm)\n\nNode / Vite starter.',
      },
    ],
  },
  {
    id: 'web-php',
    name: 'PHP web app',
    description: 'Composer-oriented PHP service with API-style layout.',
    icon: '🐘',
    defaultRepos: [
      {
        id: 'php',
        label: 'app/php',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'preview-env', 'db-postgres'],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'composer.json',
        name: 'composer.json',
        folder: '',
        content: `{\n  "name": "app/php",\n  "require": {\n    "php": ">=8.2"\n  }\n}`,
      },
      {
        path: 'public/index.php',
        name: 'index.php',
        folder: 'public',
        content: `<?php\necho json_encode(['ok' => true, 'service' => 'php']);`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# PHP web app\n\nComposer starter.',
      },
    ],
  },
  {
    id: 'mobile-ios',
    name: 'iOS app',
    description: 'Swift / Xcode-oriented mobile scaffold.',
    icon: '',
    defaultRepos: [
      {
        id: 'ios',
        label: 'app/ios',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'test-runner', 'ai-sandbox'],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'App/ContentView.swift',
        name: 'ContentView.swift',
        folder: 'App',
        content: `import SwiftUI\n\nstruct ContentView: View {\n  var body: some View {\n    Text("Hello iOS")\n  }\n}`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# iOS app\n\nSwiftUI starter.',
      },
    ],
  },
  {
    id: 'mobile-android',
    name: 'Android app',
    description: 'Kotlin / Gradle mobile scaffold.',
    icon: '🤖',
    defaultRepos: [
      {
        id: 'android',
        label: 'app/android',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'test-runner', 'ai-sandbox'],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'app/src/main/java/MainActivity.kt',
        name: 'MainActivity.kt',
        folder: 'app',
        content: `class MainActivity {\n  fun onCreate() {\n    println("Hello Android")\n  }\n}`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# Android app\n\nKotlin starter.',
      },
    ],
  },
  {
    id: 'desktop-gui',
    name: 'Desktop GUI',
    description: 'Electron / Tauri-style desktop application.',
    icon: '🖥',
    defaultRepos: [
      {
        id: 'desktop',
        label: 'app/desktop',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'preview-env', 'ai-sandbox'],
    defaultLayout: 'standard',
    seedFiles: [
      {
        path: 'src/main.ts',
        name: 'main.ts',
        folder: 'src',
        content: `// Desktop shell entry\nconsole.log('Desktop GUI ready')`,
      },
      {
        path: 'package.json',
        name: 'package.json',
        folder: '',
        content: `{\n  "name": "desktop-gui",\n  "private": true,\n  "main": "src/main.ts"\n}`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# Desktop GUI\n\nDesktop shell starter.',
      },
    ],
  },
  {
    id: 'python-api',
    name: 'Python API',
    description: 'FastAPI-style backend service for platform APIs.',
    icon: '🐍',
    defaultRepos: [
      {
        id: 'api',
        label: 'app/api',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: [
      'ci-github',
      'preview-env',
      'db-postgres',
      'test-runner',
      'ai-sandbox',
    ],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'main.py',
        name: 'main.py',
        folder: '',
        content: `from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get("/health")\ndef health():\n    return {"ok": True}`,
      },
      {
        path: 'requirements.txt',
        name: 'requirements.txt',
        folder: '',
        content: 'fastapi\nuvicorn',
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# Python API\n\nFastAPI starter.',
      },
    ],
  },
  {
    id: 'fullstack',
    name: 'Full-stack monorepo',
    description: 'Web frontend + API backend with deploy and preview harnesses.',
    icon: '▣',
    defaultRepos: [
      {
        id: 'web',
        label: 'app/web',
        url: '',
        branch: 'main',
        provider: 'github',
      },
      {
        id: 'api',
        label: 'app/api',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: [
      'ci-github',
      'preview-env',
      'deploy-k8s',
      'db-postgres',
      'test-runner',
      'ai-sandbox',
    ],
    defaultLayout: 'standard',
    seedFiles: [
      {
        path: 'apps/web/package.json',
        name: 'package.json',
        folder: 'apps/web',
        content: `{\n  "name": "web",\n  "private": true\n}`,
      },
      {
        path: 'apps/api/main.py',
        name: 'main.py',
        folder: 'apps/api',
        content: `def health():\n    return {"ok": True}`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content: '# Full-stack monorepo\n\nWeb + API starter.',
      },
    ],
  },
]

export function getTemplate(id: string | undefined): ProjectTemplate {
  return (
    PROJECT_TEMPLATES.find((t) => t.id === id) ||
    PROJECT_TEMPLATES.find((t) => t.id === 'blank')!
  )
}

export function reposFromTemplate(
  template: ProjectTemplate,
  slug: string,
): ProjectRepo[] {
  if (!template.defaultRepos.length) {
    return [
      {
        id: 'main',
        label: `${slug}/app`,
        active: true,
        branch: 'main',
        provider: 'none',
      },
    ]
  }
  return template.defaultRepos.map((r, i) => ({
    id: r.id || `repo-${i}`,
    label: r.label.includes('/')
      ? r.label.replace(/^[^/]+/, slug)
      : `${slug}/${r.label}`,
    active: i === 0,
    url: r.url || '',
    branch: r.branch || 'main',
    provider: r.provider || 'github',
  }))
}
