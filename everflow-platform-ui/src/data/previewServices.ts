export interface PreviewService {
  id: string
  label: string
  url: string
  kind: 'frontend' | 'backend' | 'admin' | 'other'
}

/** Default multi-service previews per project (demo). */
export const PREVIEW_SERVICES: Record<string, PreviewService[]> = {
  aura: [
    { id: 'web', label: 'Frontend', url: 'http://localhost:5173', kind: 'frontend' },
    { id: 'api', label: 'Backend API', url: 'http://localhost:8000', kind: 'backend' },
    { id: 'admin', label: 'Admin portal', url: 'http://localhost:3001', kind: 'admin' },
  ],
  callour: [
    { id: 'site', label: 'Marketing site', url: 'http://localhost:8080', kind: 'frontend' },
    { id: 'cms', label: 'CMS admin', url: 'http://localhost:8081', kind: 'admin' },
  ],
  router: [
    { id: 'fe', label: 'Platform UI', url: 'http://localhost:5173', kind: 'frontend' },
    { id: 'api', label: 'Platform API', url: 'http://localhost:8000', kind: 'backend' },
    { id: 'worker', label: 'Studio worker', url: 'http://localhost:8100', kind: 'backend' },
    { id: 'admin', label: 'Ops console', url: 'http://localhost:3001', kind: 'admin' },
  ],
}

export function getPreviewServices(
  projectId: string | null | undefined,
): PreviewService[] {
  if (!projectId) {
    return [
      { id: 'web', label: 'Frontend', url: 'http://localhost:5173', kind: 'frontend' },
    ]
  }
  return (
    PREVIEW_SERVICES[projectId] || [
      { id: 'web', label: 'Frontend', url: 'http://localhost:5173', kind: 'frontend' },
    ]
  )
}
