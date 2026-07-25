import { useCallback, useState } from 'react'
import type { MarketplaceItem, MarketplaceKind } from '@/data/marketplace'
import {
  getMarketplaceInstalled,
  installMarketplaceItem,
  isDemoMode,
  listProjects,
  type ApiProject,
} from '@/lib/api'
import { pushToast } from '@/lib/studioToast'
import { useAuthStore } from '@/store/authStore'
import { usePlaygroundStore } from '@/store/playgroundStore'

export function installedKey(kind: MarketplaceKind, id: string) {
  return `${kind}:${id}`
}

/** Shared install-modal state for browse + detail pages. */
export function useMarketplaceInstall() {
  const org = useAuthStore((s) => s.org)
  const demoMode = useAuthStore((s) => s.demoMode) || isDemoMode()
  const setOpenProjectModal = usePlaygroundStore((s) => s.setOpenProjectModal)
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)

  const [installItem, setInstallItem] = useState<MarketplaceItem | null>(null)
  const [projects, setProjects] = useState<ApiProject[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [installedByProject, setInstalledByProject] = useState<Record<string, Set<string>>>({})

  const refreshInstalledFor = useCallback(
    async (projectIds: string[]) => {
      if (demoMode) return
      const updates: Record<string, Set<string>> = {}
      await Promise.all(
        projectIds.map(async (pid) => {
          try {
            const res = await getMarketplaceInstalled(pid)
            updates[pid] = new Set(
              (res.items || []).map((i) => installedKey(i.kind as MarketplaceKind, i.id)),
            )
          } catch {
            /* sandbox stopped */
          }
        }),
      )
      setInstalledByProject((prev) => ({ ...prev, ...updates }))
    },
    [demoMode],
  )

  const openInstall = useCallback(
    async (item: MarketplaceItem) => {
      setInstallItem(item)
      setSelectedIds(new Set(currentProjectId ? [currentProjectId] : []))
      if (demoMode || !org?.id) {
        setProjects([])
        return
      }
      setProjectsLoading(true)
      try {
        const rows = await listProjects(org.id)
        setProjects(rows)
        const running = rows.filter((p) => p.sandbox_status === 'running').map((p) => p.id)
        if (running.length) void refreshInstalledFor(running)
      } catch (e) {
        pushToast(e instanceof Error ? e.message : 'Failed to load projects', { kind: 'danger' })
      } finally {
        setProjectsLoading(false)
      }
    },
    [currentProjectId, demoMode, org?.id, refreshInstalledFor],
  )

  const closeInstall = useCallback(() => {
    if (!installing) setInstallItem(null)
  }, [installing])

  const toggleProject = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const handleInstall = useCallback(async () => {
    if (!installItem) return
    if (demoMode) {
      pushToast('Sign in and open an API project with a running sandbox to install.', {
        kind: 'warning',
      })
      return
    }
    const targets = projects.filter((p) => selectedIds.has(p.id))
    if (!targets.length) {
      pushToast('Select at least one project', { kind: 'warning' })
      return
    }
    const blocked = targets.filter(
      (p) => p.sandbox_status !== 'running' && installItem.kind !== 'tool',
    )
    if (blocked.length) {
      pushToast(`Sandbox must be running for: ${blocked.map((p) => p.name).join(', ')}`, {
        kind: 'danger',
      })
      return
    }
    setInstalling(true)
    let ok = 0
    let fail = 0
    for (const project of targets) {
      try {
        await installMarketplaceItem(project.id, installItem.kind, installItem.id)
        ok += 1
        window.dispatchEvent(
          new CustomEvent('everflow:harness-updated', { detail: { projectId: project.id } }),
        )
      } catch (e) {
        fail += 1
        pushToast(`${project.name}: ${e instanceof Error ? e.message : 'Install failed'}`, {
          kind: 'danger',
        })
      }
    }
    setInstalling(false)
    if (ok) {
      pushToast(
        `Installed “${installItem.name}” on ${ok} project${ok === 1 ? '' : 's'}`,
        { kind: 'success' },
      )
      void refreshInstalledFor(targets.map((p) => p.id))
    }
    if (!fail) setInstallItem(null)
  }, [demoMode, installItem, projects, refreshInstalledFor, selectedIds])

  const isInstalledAnywhere = useCallback(
    (item: MarketplaceItem) => {
      const key = installedKey(item.kind, item.id)
      return Object.values(installedByProject).some((set) => set.has(key))
    },
    [installedByProject],
  )

  return {
    org,
    demoMode,
    installItem,
    projects,
    selectedIds,
    projectsLoading,
    installing,
    installedByProject,
    openInstall,
    closeInstall,
    toggleProject,
    handleInstall,
    isInstalledAnywhere,
    setOpenProjectModal,
    installedKey,
  }
}
