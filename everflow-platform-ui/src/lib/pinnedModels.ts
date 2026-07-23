/** Persist user-pinned chat models per project (localStorage). */

const PREFIX = 'everflow_pinned_models:'
const MAX_PINS = 24

export function loadPinnedModels(projectId: string): string[] {
  if (!projectId || typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(PREFIX + projectId)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.map(String).filter(Boolean).slice(0, MAX_PINS)
  } catch {
    return []
  }
}

export function savePinnedModels(projectId: string, ids: string[]): void {
  if (!projectId || typeof localStorage === 'undefined') return
  try {
    const unique = [...new Set(ids.map(String).filter(Boolean))].slice(0, MAX_PINS)
    localStorage.setItem(PREFIX + projectId, JSON.stringify(unique))
  } catch {
    /* ignore quota */
  }
}

export function togglePinnedModel(projectId: string, modelId: string): string[] {
  const cur = loadPinnedModels(projectId)
  const next = cur.includes(modelId)
    ? cur.filter((id) => id !== modelId)
    : [...cur, modelId]
  savePinnedModels(projectId, next)
  return next
}
