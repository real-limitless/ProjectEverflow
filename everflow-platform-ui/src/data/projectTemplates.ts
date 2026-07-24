import type {
  ProjectRepo,
  WorkspaceLayoutMode,
} from '@/types/project'
import type { DevicePresetId } from '@/data/devicePresets'

export type ProjectTemplateId =
  | 'blank'
  | 'web-npm'
  | 'web-php'
  | 'mobile-ios'
  | 'mobile-android'
  | 'desktop-gui'
  | 'python-api'
  | 'fullstack'

/** Shared toolkit ids (see /toolkits in the monorepo). */
export type ToolkitId =
  | 'web-npm'
  | 'web-php'
  | 'mobile-expo'
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
  /** Toolkit starter to clone/seed into the sandbox workspace. */
  toolkitId?: ToolkitId
  /** Default Preview device frame (phones for React Native templates). */
  defaultPreviewDevice?: DevicePresetId
  /**
   * Optional inline seed files for demo/local mode when no remote is cloned.
   * Prefer toolkit starters for real sandboxes.
   */
  seedFiles?: { path: string; name: string; folder: string; content: string }[]
}

/**
 * Resolve a cloneable starter URL for a toolkit.
 * Override with VITE_TOOLKIT_REPO_BASE (e.g. https://github.com/org/everflow-toolkit-{id}.git)
 * where `{id}` is replaced with the toolkit id.
 */
export function toolkitRepoUrl(toolkitId: ToolkitId): string {
  const base =
    (typeof import.meta !== 'undefined' &&
      import.meta.env?.VITE_TOOLKIT_REPO_BASE) ||
    ''
  if (typeof base === 'string' && base.trim()) {
    return base.trim().replace(/\{id\}/g, toolkitId)
  }
  // Empty → API seeds from local toolkits/ tree (TOOLKIT_LOCAL_ROOT).
  return ''
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
    defaultPreviewDevice: 'full',
  },
  {
    id: 'web-npm',
    name: 'Web app (npm / Node)',
    description: 'Vite + React frontend with package.json and Preview.',
    icon: '⬢',
    toolkitId: 'web-npm',
    defaultPreviewDevice: 'desktop',
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
    toolkitId: 'web-php',
    defaultPreviewDevice: 'desktop',
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
    name: 'iOS app (React Native)',
    description:
      'Expo / React Native — preview in an iPhone frame via Expo web (not Xcode Simulator).',
    icon: '',
    toolkitId: 'mobile-expo',
    defaultPreviewDevice: 'iphone-12',
    defaultRepos: [
      {
        id: 'mobile',
        label: 'app/mobile',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'preview-env', 'test-runner', 'ai-sandbox'],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'package.json',
        name: 'package.json',
        folder: '',
        content: `{\n  "name": "mobile-expo",\n  "private": true,\n  "main": "expo-router/entry",\n  "scripts": {\n    "start": "expo start",\n    "web": "expo start --web",\n    "android": "expo start --android",\n    "ios": "expo start --ios"\n  }\n}`,
      },
      {
        path: 'App.tsx',
        name: 'App.tsx',
        folder: '',
        content: `import { Text, View, StyleSheet } from 'react-native'\n\nexport default function App() {\n  return (\n    <View style={styles.root}>\n      <Text style={styles.title}>Hello iOS (React Native)</Text>\n      <Text>Previewed in Everflow via Expo web.</Text>\n    </View>\n  )\n}\n\nconst styles = StyleSheet.create({\n  root: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },\n  title: { fontSize: 22, fontWeight: '600', marginBottom: 8 },\n})`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content:
          '# iOS app (React Native)\n\nExpo starter — run `npm run web` and open Preview with an iPhone device frame.',
      },
    ],
  },
  {
    id: 'mobile-android',
    name: 'Android app (React Native)',
    description:
      'Expo / React Native — preview in an Android phone frame via Expo web (not an emulator).',
    icon: '🤖',
    toolkitId: 'mobile-expo',
    defaultPreviewDevice: 'pixel-7',
    defaultRepos: [
      {
        id: 'mobile',
        label: 'app/mobile',
        url: '',
        branch: 'main',
        provider: 'github',
      },
    ],
    defaultHarnessIds: ['ci-github', 'preview-env', 'test-runner', 'ai-sandbox'],
    defaultLayout: 'code-first',
    seedFiles: [
      {
        path: 'package.json',
        name: 'package.json',
        folder: '',
        content: `{\n  "name": "mobile-expo",\n  "private": true,\n  "main": "expo-router/entry",\n  "scripts": {\n    "start": "expo start",\n    "web": "expo start --web",\n    "android": "expo start --android",\n    "ios": "expo start --ios"\n  }\n}`,
      },
      {
        path: 'App.tsx',
        name: 'App.tsx',
        folder: '',
        content: `import { Text, View, StyleSheet } from 'react-native'\n\nexport default function App() {\n  return (\n    <View style={styles.root}>\n      <Text style={styles.title}>Hello Android (React Native)</Text>\n      <Text>Previewed in Everflow via Expo web.</Text>\n    </View>\n  )\n}\n\nconst styles = StyleSheet.create({\n  root: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },\n  title: { fontSize: 22, fontWeight: '600', marginBottom: 8 },\n})`,
      },
      {
        path: 'README.md',
        name: 'README.md',
        folder: '',
        content:
          '# Android app (React Native)\n\nExpo starter — run `npm run web` and open Preview with a Pixel / Z Fold device frame.',
      },
    ],
  },
  {
    id: 'desktop-gui',
    name: 'Desktop GUI',
    description: 'Electron-style desktop application shell.',
    icon: '🖥',
    toolkitId: 'desktop-gui',
    defaultPreviewDevice: 'desktop',
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
    toolkitId: 'python-api',
    defaultPreviewDevice: 'desktop',
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
    toolkitId: 'fullstack',
    defaultPreviewDevice: 'desktop',
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
  const starterUrl = template.toolkitId
    ? toolkitRepoUrl(template.toolkitId)
    : ''
  return template.defaultRepos.map((r, i) => ({
    id: r.id || `repo-${i}`,
    label: r.label.includes('/')
      ? r.label.replace(/^[^/]+/, slug)
      : `${slug}/${r.label}`,
    active: i === 0,
    // First repo gets the toolkit starter URL when configured.
    url: (i === 0 && starterUrl ? starterUrl : r.url) || '',
    branch: r.branch || 'main',
    provider: r.provider || (starterUrl && i === 0 ? 'github' : 'github'),
  }))
}
