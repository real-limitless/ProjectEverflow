/**
 * Pure helpers for reconciling the local project catalog with the API list.
 * Live (non-demo) mode treats the API as source of truth; localStorage is a cache.
 */

export interface CatalogProjectRef {
  id: string
  /** True when the entry was hydrated from / created via the platform API */
  fromApi?: boolean
}

/**
 * Select catalog project ids that should be removed after a successful API list.
 *
 * - Demo mode: never prune (caller should skip reconcile entirely).
 * - Pure offline seeds (no fromApi): leave in catalog; UI already hides them.
 * - Non-seed ids not present in the API list: stale → remove.
 * - Seed ids that were marked fromApi but are absent from API: also stale
 *   (should not happen with real UUIDs, but keeps catalog honest).
 */
export function selectStaleProjectIds(
  catalog: CatalogProjectRef[],
  apiIds: Iterable<string>,
  options?: {
    demoMode?: boolean
    seedIds?: Set<string> | ReadonlySet<string>
  },
): string[] {
  if (options?.demoMode) return []

  const valid = apiIds instanceof Set ? apiIds : new Set(apiIds)
  const seeds = options?.seedIds ?? new Set<string>()
  const stale: string[] = []

  for (const entry of catalog) {
    const id = entry?.id
    if (!id) continue
    if (valid.has(id)) continue

    const isSeed = seeds.has(id)
    if (isSeed && !entry.fromApi) {
      // Offline demo seed — keep hardcoded entry
      continue
    }
    // Non-seed missing from API, or seed that claimed to be API-backed
    stale.push(id)
  }

  return stale
}

/** Drop open-tab ids that are no longer in the catalog or known-stale. */
export function filterOpenIdsAfterPurge(
  openProjectIds: string[],
  removedIds: Iterable<string>,
  stillInCatalog: (id: string) => boolean,
): string[] {
  const removed = removedIds instanceof Set ? removedIds : new Set(removedIds)
  return openProjectIds.filter((id) => !removed.has(id) && stillInCatalog(id))
}

/**
 * Resolve current project after purging ids.
 * Prefers previous current if still open; else first open; else null.
 */
export function resolveCurrentAfterPurge(
  previousCurrent: string | null,
  openProjectIds: string[],
): string | null {
  if (previousCurrent && openProjectIds.includes(previousCurrent)) {
    return previousCurrent
  }
  return openProjectIds[0] ?? null
}
