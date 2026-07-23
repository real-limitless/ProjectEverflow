import { create } from 'zustand'
import { PANEL_META } from '@/data/panelMeta'
import {
  createProjectFromDraft,
  type CreateProjectDraft,
} from '@/data/createProjectDraft'
import {
  DEFAULT_AGENT_HARNESS_IDS,
  harnessesFromApi,
  harnessesFromIds,
} from '@/data/harnesses'
import {
  PROJECTS,
  addProjectToCatalog,
  createBlankProject,
  getProject,
  isSeedProjectId,
  listUserCreatedProjects,
  mergeUserProjects,
  slugifyProjectName,
  updateProjectInCatalog,
} from '@/data/projects'
import type { Project } from '@/types/project'
import type { WorkspaceLayoutMode } from '@/types/project'
import {
  addPanelToGroup,
  addTabToGroup,
  allPanelsInLayout,
  cloneLayout,
  countTypeInLayout,
  firstGroup,
  movePanelToGroupAt,
  removePanelFromLayout,
  setActiveTab,
  setSizesAtPath,
  splitGroup,
} from '@/lib/dockTree'
import { emptyGroup, loadPersisted, savePersisted } from '@/lib/layoutPersist'
import {
  applyThemeClass,
  deleteNamedLayout as deleteNamedLayoutStorage,
  listNamedLayouts as readNamedLayouts,
  loadTheme,
  saveNamedLayout as persistNamedLayout,
  saveTheme,
  type NamedLayoutSnapshot,
  type ThemeMode,
} from '@/lib/namedLayouts'
import { typeOf } from '@/lib/panelIds'
import type { DropEdge, LayoutNode } from '@/types/dock'
import type { PanelInstanceState, PanelKey, PanelType } from '@/types/panels'
import type { PaletteMode } from '@/types/project'
import {
  DEFAULT_CHAT_AGENTS,
  DEFAULT_CHAT_MCPS,
  DEFAULT_CHAT_MODEL,
  DEFAULT_CHAT_MODE,
  DEFAULT_CHAT_SKILLS,
  DEFAULT_CHAT_TOOLS,
  DEFAULT_PRIMARY_AGENT,
  agentById,
} from '@/data/chatCatalog'
import {
  cloneConversations,
  demoAssistantReply,
  emptyConversation,
  findConversation,
  seedProjectConversations,
  sortConversations,
  syncPanelFromConversation,
  updateConvMetrics,
  deriveTitleFromMessages,
  newMessageId,
  cloneMessages,
} from '@/lib/chatConversation'
import type { ChatConversation, ChatMessage, ChatMode } from '@/types/panels'
import {
  createProject as apiCreateProject,
  isDemoMode,
  type ApiProject,
} from '@/lib/api'
import { useAuthStore } from '@/store/authStore'
import { getPlaygroundFloatPalettePos } from '@/lib/palettePosition'
import { pushToast } from '@/lib/studioToast'

interface PlaygroundState {
  openProjectIds: string[]
  /** null when no project tab is open */
  currentProjectId: string | null
  layout: LayoutNode
  projectLayouts: Record<string, LayoutNode>
  instanceState: Record<string, PanelInstanceState>
  /** Working copy of conversations per project (mutable demo state) */
  projectChats: Record<string, ChatConversation[]>
  groupIdSeq: number
  instanceSeq: number
  sidebarCollapsed: boolean
  isSidebarOpen: boolean
  paletteMode: PaletteMode
  palettePos: { x: number; y: number }
  paletteVisible: boolean
  openProjectModal: boolean
  createProjectModal: boolean
  connectRepoModal: boolean
  projectSettingsOpen: boolean
  /** Project id targeted by Project settings (defaults to current when opening) */
  projectSettingsProjectId: string | null
  dragPanelId: string | null
  detachedPanels: Set<string>
  theme: ThemeMode
  paletteDragging: boolean
  /** Bumps when catalog gains a user-created project (forces UI refresh) */
  catalogVersion: number
  /** Prefill Terminal input (e.g. from Agents panel) */
  terminalPrefill: string | null
  /** Per-project active repository id (Repository panel + repo strip) */
  activeRepoByProject: Record<string, string>

  // derived helpers exposed as methods
  nextGroupId: () => string
  spawnPanelKey: (type: PanelType, opts?: Partial<PanelInstanceState>) => PanelKey
  ensureInstanceState: (key: PanelKey, opts?: Partial<PanelInstanceState>) => PanelInstanceState
  panelTabLabel: (key: PanelKey) => string
  getLayout: () => LayoutNode
  setLayout: (layout: LayoutNode) => void
  persist: () => void
  /** Resolve active repo for a project (store override → catalog active flag → first). */
  getActiveRepoId: (projectId?: string | null) => string

  setSidebarCollapsed: (v: boolean) => void
  setSidebarOpen: (v: boolean) => void
  setPaletteMode: (mode: PaletteMode) => void
  setPalettePos: (pos: { x: number; y: number }) => void
  setPaletteVisible: (v: boolean) => void
  setOpenProjectModal: (v: boolean) => void
  setCreateProjectModal: (v: boolean) => void
  setConnectRepoModal: (v: boolean) => void
  openProjectSettings: (projectId?: string | null) => void
  closeProjectSettings: () => void
  updateProject: (projectId: string, patch: Partial<Project>) => boolean
  setDragPanelId: (id: string | null) => void
  setPaletteDragging: (v: boolean) => void
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
  saveNamedLayout: (name: string) => void
  loadNamedLayout: (id: string) => boolean
  listNamedLayouts: () => NamedLayoutSnapshot[]
  deleteNamedLayout: (id: string) => void

  switchProject: (id: string) => void
  openProject: (id: string) => void
  closeProjectTab: (id: string) => void
  setTerminalPrefill: (cmd: string | null) => void
  clearTerminalPrefill: () => void
  createProject: (
    draft: import('@/data/createProjectDraft').CreateProjectDraft | string,
  ) => Promise<string | null>
  /** Hydrate an API project into the local catalog and open it */
  ingestApiProject: (
    apiProject: ApiProject,
    seed?: Partial<Project>,
  ) => void
  patchProjectSandbox: (
    projectId: string,
    patch: {
      sandboxStatus?: string
      sandboxName?: string | null
      sandboxError?: string | null
      sandboxImage?: string | null
      sandboxCreatedAt?: string | null
    },
  ) => void
  resetLayout: () => void

  activateTab: (groupId: string, panelId: PanelKey) => void
  closePanel: (panelId: PanelKey) => void
  duplicatePanel: (groupId: string, panelId: PanelKey) => void
  openPanelType: (type: PanelType) => void
  dropPanel: (panelId: PanelKey, groupId: string, edge: DropEdge) => void
  movePanelToGroup: (
    panelId: PanelKey,
    groupId: string,
    insertIndex?: number,
  ) => void
  resizeSplit: (pathToSplit: number[], sizes: number[]) => void
  setActiveRepo: (repoId: string, projectId?: string | null) => void

  ensureProjectChats: (projectId: string | null | undefined) => ChatConversation[]
  getConversations: (projectId?: string | null) => ChatConversation[]
  getActiveConversation: (panelKey: PanelKey) => ChatConversation | undefined
  appendChatMessage: (panelKey: PanelKey, text: string) => void
  setChatConv: (panelKey: PanelKey, convId: string) => void
  newChatConversation: (panelKey: PanelKey) => void
  renameConversation: (projectId: string, convId: string, title: string) => void
  deleteConversation: (projectId: string, convId: string, panelKey?: PanelKey) => void
  pinConversation: (projectId: string, convId: string, pinned?: boolean) => void
  aiTitleConversation: (projectId: string, convId: string) => void
  forkConversation: (panelKey: PanelKey, fromMessageId: string) => void
  editUserMessage: (panelKey: PanelKey, messageId: string, text: string) => void
  retryAssistantMessage: (panelKey: PanelKey, messageId: string) => void
  setChatMode: (panelKey: PanelKey, mode: ChatMode) => void
  setConversationAgents: (panelKey: PanelKey, agentIds: string[]) => void
  /** Set primary OpenCode agent for this conversation (plan, build, …) */
  setConversationAgent: (panelKey: PanelKey, agentName: string) => void
  updateConversationMessages: (
    projectId: string,
    convId: string,
    messages: ChatMessage[],
    lastAssistant?: ChatMessage,
  ) => void

  setCodeFile: (panelKey: PanelKey, file: string) => void
  openCodeFile: (panelKey: PanelKey, filePath: string) => void
  closeCodeFile: (panelKey: PanelKey, filePath: string) => void
  setCodeFontSize: (panelKey: PanelKey, size: number) => void
  toggleCodeFolder: (panelKey: PanelKey, folderPath: string) => void
  detachPanel: (panelId: PanelKey) => void
  reattachPanel: (panelId: PanelKey) => void
}

function seedInstances(
  spawn: (type: PanelType) => PanelKey,
): Record<string, PanelKey> {
  return {
    chat: spawn('chat'),
    preview: spawn('preview'),
    knowledge: spawn('knowledge'),
    code: spawn('code'),
    repository: spawn('repository'),
    terminal: spawn('terminal'),
  }
}

/** Expand top-level folders (and shallow parents) so the tree is usable on first open. */
function defaultExpandedFolders(
  files: { path: string }[] | undefined,
): string[] {
  if (!files?.length) return []
  const dirs = new Set<string>()
  for (const f of files) {
    const parts = f.path.split('/').filter(Boolean)
    if (parts.length > 1) dirs.add(parts[0])
    // expand one more level when deeply nested so demos show content
    if (parts.length > 2) dirs.add(parts.slice(0, 2).join('/'))
  }
  return [...dirs]
}

const CODE_FONT_MIN = 10
const CODE_FONT_MAX = 22

function buildDefaultLayout(
  nextGroupId: () => string,
  spawn: (type: PanelType, opts?: Partial<PanelInstanceState>) => PanelKey,
  ensure: (key: PanelKey, opts?: Partial<PanelInstanceState>) => void,
  projectId: string,
  chats?: ChatConversation[],
  layoutMode: WorkspaceLayoutMode = 'standard',
): LayoutNode {
  const keys = seedInstances((t) => {
    const k = spawn(t)
    ensure(k)
    return k
  })
  // seed chat with project conversations
  const p = PROJECTS[projectId]
  const convList = chats?.length ? chats : seedProjectConversations(projectId)
  const primary = convList[0]
  if (p && primary) {
    ensure(keys.chat, {
      ...syncPanelFromConversation(primary),
      model: DEFAULT_CHAT_MODEL,
      enabledTools: DEFAULT_CHAT_TOOLS,
      enabledMcps: DEFAULT_CHAT_MCPS,
      enabledSkills: DEFAULT_CHAT_SKILLS,
    })
    const first = p.files[0]?.path || p.files[0]?.name
    ensure(keys.code, {
      file: first,
      openFiles: first ? [first] : [],
      codeFontSize: 12,
      expandedFolders: defaultExpandedFolders(p.files),
    })
  }

  if (layoutMode === 'chat-first') {
    return {
      type: 'split',
      direction: 'horizontal',
      sizes: [55, 45],
      children: [
        {
          type: 'group',
          id: nextGroupId(),
          tabs: [keys.chat],
          active: keys.chat,
        },
        {
          type: 'group',
          id: nextGroupId(),
          tabs: [keys.preview, keys.code, keys.terminal, keys.repository],
          active: keys.preview,
        },
      ],
    }
  }

  if (layoutMode === 'code-first') {
    return {
      type: 'split',
      direction: 'horizontal',
      sizes: [55, 45],
      children: [
        {
          type: 'group',
          id: nextGroupId(),
          tabs: [keys.code, keys.repository, keys.knowledge],
          active: keys.code,
        },
        {
          type: 'split',
          direction: 'vertical',
          sizes: [60, 40],
          children: [
            {
              type: 'group',
              id: nextGroupId(),
              tabs: [keys.preview, keys.chat],
              active: keys.preview,
            },
            {
              type: 'group',
              id: nextGroupId(),
              tabs: [keys.terminal],
              active: keys.terminal,
            },
          ],
        },
      ],
    }
  }

  return {
    type: 'split',
    direction: 'horizontal',
    sizes: [40, 60],
    children: [
      {
        type: 'group',
        id: nextGroupId(),
        tabs: [keys.chat],
        active: keys.chat,
      },
      {
        type: 'split',
        direction: 'vertical',
        sizes: [70, 30],
        children: [
          {
            type: 'group',
            id: nextGroupId(),
            tabs: [keys.preview, keys.knowledge, keys.code, keys.repository],
            active: keys.preview,
          },
          {
            type: 'group',
            id: nextGroupId(),
            tabs: [keys.terminal],
            active: keys.terminal,
          },
        ],
      },
    ],
  }
}

/** Drop pure offline demo seeds from restored open tabs when not in demo mode. */
function filterOpenProjectIds(ids: string[]): string[] {
  return ids.filter((id) => {
    if (!PROJECTS[id]) return false
    if (isDemoMode()) return true
    if (isSeedProjectId(id) && !PROJECTS[id].fromApi) return false
    return true
  })
}

function createInitial() {
  let groupIdSeq = 1
  let instanceSeq = 1
  const instanceState: Record<string, PanelInstanceState> = {}
  const projectChats: Record<string, ChatConversation[]> = {}

  const nextGroupId = () => `g${groupIdSeq++}`
  const spawnPanelKey = (type: PanelType, opts: Partial<PanelInstanceState> = {}): PanelKey => {
    const key = `${type}:${instanceSeq++}` as PanelKey
    instanceState[key] = { type, ...opts }
    return key
  }
  const ensureInstanceState = (key: PanelKey, opts: Partial<PanelInstanceState> = {}) => {
    if (!instanceState[key]) {
      const type = typeOf(key) as PanelType
      instanceState[key] = { type, ...opts }
    } else if (Object.keys(opts).length) {
      Object.assign(instanceState[key], opts)
    }
    return instanceState[key]
  }

  // Clean slate: no demo projects auto-opened (use Create / Open project).
  const projectLayouts: Record<string, LayoutNode> = {}
  const emptyLayout = emptyGroup('g-empty')

  const persisted = loadPersisted()
  if (persisted) {
    // Restore user-created projects before validating open ids
    mergeUserProjects(persisted.userProjects)

    const rawOpen = Array.isArray(persisted.openProjectIds) ? persisted.openProjectIds : []
    // Preserve empty list when user closed all projects; strip demo seeds outside demo mode
    const ids = filterOpenProjectIds(rawOpen)
    const persistedCurrent = persisted.currentProjectId
    const currentProjectId =
      persistedCurrent && PROJECTS[persistedCurrent] && ids.includes(persistedCurrent)
        ? persistedCurrent
        : ids[0] ?? null

    if (currentProjectId) {
      projectChats[currentProjectId] = seedProjectConversations(currentProjectId)
    }

    let nextLayout = emptyGroup('g-empty')
    if (currentProjectId) {
      nextLayout = persisted.projectLayouts[currentProjectId]
        ? cloneLayout(persisted.projectLayouts[currentProjectId])
        : buildDefaultLayout(
            nextGroupId,
            spawnPanelKey,
            ensureInstanceState,
            currentProjectId,
            projectChats[currentProjectId],
          )
    }

    // Refresh chat instance messages from seeds when present
    const restoredState = { ...(persisted.instanceState || instanceState) }
    if (currentProjectId && projectChats[currentProjectId]?.[0]) {
      for (const [key, st] of Object.entries(restoredState)) {
        if (st.type === 'chat' || key.startsWith('chat:')) {
          const conv =
            findConversation(projectChats[currentProjectId], st.convId) ||
            projectChats[currentProjectId][0]
          Object.assign(st, syncPanelFromConversation(conv))
        }
      }
    }

    return {
      openProjectIds: ids,
      currentProjectId,
      layout: nextLayout,
      projectLayouts: { ...projectLayouts, ...persisted.projectLayouts },
      instanceState: restoredState,
      projectChats,
      groupIdSeq: persisted.groupIdSeq || groupIdSeq,
      instanceSeq: persisted.instanceSeq || instanceSeq,
      paletteMode: persisted.paletteMode || ('float' as PaletteMode),
      palettePos: persisted.palettePos || {
        // Bottom-center-ish fallback; refined when tray is shown
        x: Math.max(24, (typeof window !== 'undefined' ? window.innerWidth : 1200) / 2 - 220),
        y: Math.max(72, (typeof window !== 'undefined' ? window.innerHeight : 800) - 200),
      },
      catalogVersion: 0,
      activeRepoByProject: {},
    }
  }

  return {
    openProjectIds: [] as string[],
    currentProjectId: null as string | null,
    layout: emptyLayout,
    projectLayouts,
    instanceState,
    projectChats,
    groupIdSeq,
    instanceSeq,
    paletteMode: 'float' as PaletteMode,
    palettePos: {
      x:
        typeof window !== 'undefined'
          ? Math.max(24, window.innerWidth / 2 - 220)
          : 400,
      y:
        typeof window !== 'undefined'
          ? Math.max(72, window.innerHeight - 200)
          : 600,
    },
    catalogVersion: 0,
    terminalPrefill: null as string | null,
    activeRepoByProject: {},
  }
}

const initial = createInitial()

export const usePlaygroundStore = create<PlaygroundState>((set, get) => ({
  ...initial,
  projectChats: initial.projectChats || {},
  sidebarCollapsed: false,
  isSidebarOpen: true,
  paletteVisible: true,
  openProjectModal: false,
  createProjectModal: false,
  connectRepoModal: false,
  projectSettingsOpen: false,
  projectSettingsProjectId: null,
  dragPanelId: null,
  detachedPanels: new Set(),
  theme: typeof document !== 'undefined' ? loadTheme() : 'light',
  paletteDragging: false,
  terminalPrefill: null,
  activeRepoByProject: initial.activeRepoByProject || {},

  setTerminalPrefill: (cmd) => set({ terminalPrefill: cmd }),
  clearTerminalPrefill: () => set({ terminalPrefill: null }),

  getActiveRepoId: (projectId) => {
    const id = projectId === undefined ? get().currentProjectId : projectId
    if (!id) return ''
    const override = get().activeRepoByProject[id]
    const p = getProject(id)
    const repos = p?.repos || []
    if (override && repos.some((r) => r.id === override)) return override
    return repos.find((r) => r.active)?.id || repos[0]?.id || ''
  },

  nextGroupId: () => {
    const id = `g${get().groupIdSeq}`
    set({ groupIdSeq: get().groupIdSeq + 1 })
    return id
  },

  spawnPanelKey: (type, opts = {}) => {
    const seq = get().instanceSeq
    const key = `${type}:${seq}` as PanelKey
    set({
      instanceSeq: seq + 1,
      instanceState: {
        ...get().instanceState,
        [key]: { type, ...opts },
      },
    })
    return key
  },

  ensureInstanceState: (key, opts = {}) => {
    const state = get().instanceState
    if (!state[key]) {
      const type = (typeOf(key) || 'chat') as PanelType
      const next = { ...state, [key]: { type, ...opts } }
      set({ instanceState: next })
      return next[key]
    }
    if (Object.keys(opts).length) {
      const next = {
        ...state,
        [key]: { ...state[key], ...opts },
      }
      set({ instanceState: next })
      return next[key]
    }
    return state[key]
  },

  panelTabLabel: (key) => {
    const type = typeOf(key)
    const meta = type ? PANEL_META[type] : null
    if (!meta) return String(key)
    const st = get().instanceState[key]
    if (type === 'chat' && st?.title) {
      return `${meta.label} · ${st.title}`
    }
    const n = countTypeInLayout(type, get().layout)
    if (n > 1) {
      const idPart = String(key).split(':')[1] || ''
      return `${meta.label} ${idPart}`
    }
    return meta.label
  },

  getLayout: () => get().layout,

  setLayout: (layout) => {
    set({ layout })
    get().persist()
  },

  persist: () => {
    const s = get()
    const projectLayouts = { ...s.projectLayouts }
    if (s.currentProjectId) {
      projectLayouts[s.currentProjectId] = cloneLayout(s.layout)
    }
    set({ projectLayouts })
    savePersisted({
      openProjectIds: s.openProjectIds,
      currentProjectId: s.currentProjectId,
      groupIdSeq: s.groupIdSeq,
      instanceSeq: s.instanceSeq,
      instanceState: s.instanceState,
      projectLayouts,
      paletteMode: s.paletteMode,
      palettePos: s.palettePos,
      userProjects: listUserCreatedProjects(),
    })
  },

  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  setSidebarOpen: (v) => set({ isSidebarOpen: v }),
  setPaletteMode: (mode) => {
    set({ paletteMode: mode, paletteVisible: mode !== 'chip' })
    get().persist()
  },
  setPalettePos: (pos) => {
    set({ palettePos: pos })
    get().persist()
  },
  setPaletteVisible: (v) => set({ paletteVisible: v }),
  setOpenProjectModal: (v) => set({ openProjectModal: v }),
  setCreateProjectModal: (v) => set({ createProjectModal: v }),
  setConnectRepoModal: (v) => set({ connectRepoModal: v }),

  openProjectSettings: (projectId) => {
    const id = projectId || get().currentProjectId
    if (!id || !PROJECTS[id]) return
    set({
      projectSettingsOpen: true,
      projectSettingsProjectId: id,
    })
  },

  closeProjectSettings: () => {
    set({ projectSettingsOpen: false, projectSettingsProjectId: null })
  },

  updateProject: (projectId, patch) => {
    const updated = updateProjectInCatalog(projectId, patch)
    if (!updated) return false
    set({ catalogVersion: get().catalogVersion + 1 })
    get().persist()
    return true
  },

  setDragPanelId: (id) => set({ dragPanelId: id }),
  setPaletteDragging: (v) => set({ paletteDragging: v }),

  setTheme: (theme) => {
    applyThemeClass(theme)
    saveTheme(theme)
    set({ theme })
  },
  toggleTheme: () => {
    const next: ThemeMode = get().theme === 'dark' ? 'light' : 'dark'
    get().setTheme(next)
  },

  saveNamedLayout: (name) => {
    const s = get()
    const trimmed = name.trim()
    if (!trimmed || !s.currentProjectId) return
    persistNamedLayout({
      id: `nl-${Date.now()}`,
      name: trimmed,
      savedAt: new Date().toISOString(),
      projectId: s.currentProjectId,
      layout: cloneLayout(s.layout),
      instanceState: JSON.parse(JSON.stringify(s.instanceState)) as Record<
        string,
        PanelInstanceState
      >,
      groupIdSeq: s.groupIdSeq,
      instanceSeq: s.instanceSeq,
    })
  },

  loadNamedLayout: (id) => {
    const snap = readNamedLayouts().find((s) => s.id === id)
    if (!snap) return false
    set({
      layout: cloneLayout(snap.layout),
      instanceState: JSON.parse(JSON.stringify(snap.instanceState)) as Record<
        string,
        PanelInstanceState
      >,
      groupIdSeq: snap.groupIdSeq,
      instanceSeq: snap.instanceSeq,
    })
    get().persist()
    return true
  },

  listNamedLayouts: () => readNamedLayouts(),
  deleteNamedLayout: (id) => deleteNamedLayoutStorage(id),

  switchProject: (id) => {
    if (!getProject(id)) return
    // Block pure demo seeds outside demo mode
    if (!isDemoMode() && isSeedProjectId(id) && !getProject(id)?.fromApi) return
    const s = get()
    if (id === s.currentProjectId) return
    const projectLayouts = { ...s.projectLayouts }
    if (s.currentProjectId) {
      projectLayouts[s.currentProjectId] = cloneLayout(s.layout)
    }
    // Ensure conversations for target project exist before layout seed
    if (!s.projectChats[id]?.length) {
      set({
        projectChats: {
          ...get().projectChats,
          [id]: seedProjectConversations(id),
        },
      })
    }
    const chats = get().projectChats[id]
    let layout = projectLayouts[id]
    if (!layout) {
      layout = buildDefaultLayout(
        () => get().nextGroupId(),
        (t, o) => get().spawnPanelKey(t, o),
        (k, o) => {
          get().ensureInstanceState(k, o)
        },
        id,
        chats,
      )
      projectLayouts[id] = cloneLayout(layout)
    } else {
      layout = cloneLayout(layout)
    }
    const openProjectIds = s.openProjectIds.includes(id)
      ? s.openProjectIds
      : [...s.openProjectIds, id]
    set({ currentProjectId: id, layout, projectLayouts, openProjectIds })
    get().persist()
  },

  openProject: (id) => {
    get().switchProject(id)
    set({ openProjectModal: false, createProjectModal: false })
  },

  closeProjectTab: (id) => {
    const s = get()
    const projectLayouts = { ...s.projectLayouts }
    if (s.currentProjectId) {
      projectLayouts[s.currentProjectId] = cloneLayout(s.layout)
    }
    const openProjectIds = s.openProjectIds.filter((x) => x !== id)
    if (openProjectIds.length === 0) {
      set({
        openProjectIds: [],
        currentProjectId: null,
        projectLayouts,
        layout: emptyGroup('g-empty'),
      })
      get().persist()
      return
    }
    if (s.currentProjectId === id) {
      const next = openProjectIds[0]
      set({ openProjectIds, projectLayouts })
      get().switchProject(next)
    } else {
      set({ openProjectIds, projectLayouts })
      get().persist()
    }
  },

  ingestApiProject: (apiProject, seed) => {
    const existing = getProject(apiProject.id)
    const project: Project = {
      id: apiProject.id,
      name: apiProject.name,
      slug: apiProject.slug,
      description: apiProject.description || '',
      fromApi: true,
      organizationId: apiProject.organization_id,
      sandboxName: apiProject.sandbox_name,
      sandboxStatus: apiProject.sandbox_status || 'pending',
      sandboxImage: apiProject.sandbox_image,
      sandboxError: apiProject.sandbox_error,
      sandboxCreatedAt: apiProject.sandbox_created_at,
      templateId: existing?.templateId || seed?.templateId || 'blank',
      layoutMode: existing?.layoutMode || seed?.layoutMode || 'standard',
      environment: existing?.environment || seed?.environment || 'local',
      visibility: existing?.visibility || seed?.visibility || 'private',
      harnesses: (() => {
        if (apiProject.harnesses?.length) {
          return harnessesFromApi(apiProject.harnesses)
        }
        if (existing?.harnesses?.length) return existing.harnesses
        if (seed?.harnesses?.length) return seed.harnesses
        return harnessesFromIds([...DEFAULT_AGENT_HARNESS_IDS])
      })(),
      repos: (() => {
        const fromApi = apiProject.repos?.length
          ? apiProject.repos.map((r, i) => ({
              id: r.id || `repo-${i}`,
              label: r.label || r.id || `repo-${i}`,
              active: Boolean(r.active),
              url: r.url || undefined,
              branch: r.branch || 'main',
              provider: (r.provider as import('@/types/project').RepoProvider) || 'github',
              localPath: r.local_path || undefined,
              cloneStatus: r.clone_status || undefined,
              cloneError: r.clone_error || undefined,
            }))
          : null
        if (fromApi?.length) {
          if (!fromApi.some((r) => r.active)) fromApi[0].active = true
          return fromApi
        }
        return (
          existing?.repos ||
          seed?.repos || [
            {
              id: 'main',
              label: `${apiProject.slug}/app`,
              active: true,
              branch: 'main',
              provider: 'none' as const,
            },
          ]
        )
      })(),
      convs: existing?.convs || seed?.convs || [{ id: 'c1', title: 'New chat', meta: 'Just now' }],
      messages: existing?.messages || seed?.messages || [],
      files: existing?.files || seed?.files || [{ path: 'README.md', name: 'README.md', folder: '' }],
      code: existing?.code || seed?.code || {
        'README.md': `# ${apiProject.name}\n\n${apiProject.description || 'Everflow project.'}\n`,
      },
      knowledgeFiles: existing?.knowledgeFiles || seed?.knowledgeFiles || [],
      canvases: existing?.canvases || seed?.canvases || [],
      termLines:
        existing?.termLines ||
        seed?.termLines ||
        [
          { cls: 'muted', text: `sandbox@${apiProject.slug}:~$` },
          { cls: '', text: 'Connected to project sandbox' },
        ],
    }
    addProjectToCatalog(project)
    set({ catalogVersion: get().catalogVersion + 1 })
    get().persist()
  },

  patchProjectSandbox: (projectId, patch) => {
    const p = getProject(projectId)
    if (!p) return
    updateProjectInCatalog(projectId, {
      sandboxStatus: patch.sandboxStatus ?? p.sandboxStatus,
      sandboxName: patch.sandboxName !== undefined ? patch.sandboxName : p.sandboxName,
      sandboxError: patch.sandboxError !== undefined ? patch.sandboxError : p.sandboxError,
      sandboxImage: patch.sandboxImage !== undefined ? patch.sandboxImage : p.sandboxImage,
      sandboxCreatedAt:
        patch.sandboxCreatedAt !== undefined ? patch.sandboxCreatedAt : p.sandboxCreatedAt,
    })
    set({ catalogVersion: get().catalogVersion + 1 })
    get().persist()
  },

  createProject: async (input) => {
    let draft: CreateProjectDraft
    if (typeof input === 'string') {
      const trimmed = input.trim()
      if (!trimmed) return null
      draft = {
        name: trimmed,
        templateId: 'blank',
        repos: [],
        harnessIds: ['agent-claude-code', 'agent-opencode'],
        options: {
          layout: 'standard',
          includeSampleData: false,
          environment: 'local',
          visibility: 'private',
          dockPalette: true,
        },
      }
    } else {
      if (!input.name.trim()) return null
      draft = input
    }

    let project: Project
    const demo = isDemoMode()
    const auth = useAuthStore.getState()

    if (!demo && auth.user && auth.org) {
      const slug = draft.slug?.trim() || slugifyProjectName(draft.name)
      try {
        const { projectReposToApiPayload, normalizeReposForCreate } = await import(
          '@/lib/workspaceRepos'
        )
        const normalizedRepos = normalizeReposForCreate(draft.repos || [])
        const harnessIds =
          draft.harnessIds.length > 0
            ? draft.harnessIds
            : [...DEFAULT_AGENT_HARNESS_IDS]
        const apiProject = await apiCreateProject(auth.org.id, {
          name: draft.name.trim(),
          slug,
          description: draft.description?.trim() || undefined,
          repos: projectReposToApiPayload(normalizedRepos),
          harnesses: harnessIds,
        })
        project = createProjectFromDraft(
          { ...draft, repos: normalizedRepos },
          { apiProject },
        )
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Create project failed'
        pushToast(msg, { kind: 'danger' })
        return null
      }
    } else {
      project =
        typeof input === 'string'
          ? createBlankProject(input)
          : createProjectFromDraft(draft)
    }

    addProjectToCatalog(project)
    get().ensureProjectChats(project.id)

    const layout = buildDefaultLayout(
      () => get().nextGroupId(),
      (t, o) => get().spawnPanelKey(t, o),
      (k, o) => {
        get().ensureInstanceState(k, o)
      },
      project.id,
      undefined,
      project.layoutMode || draft.options.layout,
    )
    const s = get()
    const projectLayouts = { ...s.projectLayouts }
    if (s.currentProjectId) {
      projectLayouts[s.currentProjectId] = cloneLayout(s.layout)
    }
    projectLayouts[project.id] = cloneLayout(layout)
    const openProjectIds = s.openProjectIds.includes(project.id)
      ? s.openProjectIds
      : [...s.openProjectIds, project.id]
    set({
      openProjectIds,
      currentProjectId: project.id,
      layout,
      projectLayouts,
      catalogVersion: s.catalogVersion + 1,
      createProjectModal: false,
      openProjectModal: false,
      paletteMode: draft.options.dockPalette ? s.paletteMode : s.paletteMode,
      paletteVisible: draft.options.dockPalette ? true : s.paletteVisible,
    })
    get().persist()

    // API projects open into SandboxBootGate (PlaygroundPage) which owns
    // ensure/poll until sandbox_status === running. Do not mount workbench early.

    return project.id
  },

  resetLayout: () => {
    const id = get().currentProjectId
    if (!id) return
    const layout = buildDefaultLayout(
      () => get().nextGroupId(),
      (t, o) => get().spawnPanelKey(t, o),
      (k, o) => {
        get().ensureInstanceState(k, o)
      },
      id,
    )
    set({ layout })
    get().persist()
  },

  activateTab: (groupId, panelId) => {
    set({ layout: setActiveTab(get().layout, groupId, panelId) })
    get().persist()
  },

  closePanel: (panelId) => {
    const layout = removePanelFromLayout(get().layout, panelId, () => get().nextGroupId())
    set({ layout })
    // Keep panel tray discoverable after close (bottom-center of playground)
    if (get().paletteMode === 'chip' || !get().paletteVisible) {
      set({
        paletteVisible: true,
        paletteMode: 'float',
        palettePos: getPlaygroundFloatPalettePos(),
      })
    }
    get().persist()
  },

  duplicatePanel: (groupId, panelId) => {
    const type = typeOf(panelId) as PanelType
    if (!type) return
    const opts: Partial<PanelInstanceState> = {}
    if (type === 'chat') {
      const conv = emptyConversation()
      const projectId = get().currentProjectId
      if (projectId) {
        const list = [conv, ...get().ensureProjectChats(projectId)]
        set({ projectChats: { ...get().projectChats, [projectId]: list } })
      }
      Object.assign(opts, syncPanelFromConversation(conv), {
        model: DEFAULT_CHAT_MODEL,
        enabledTools: DEFAULT_CHAT_TOOLS,
        enabledMcps: DEFAULT_CHAT_MCPS,
        enabledSkills: DEFAULT_CHAT_SKILLS,
      })
    }
    const key = get().spawnPanelKey(type, opts)
    const layout = addTabToGroup(get().layout, groupId, key)
    set({ layout })
    get().persist()
  },

  openPanelType: (type) => {
    const key = get().spawnPanelKey(type)
    get().ensureInstanceState(key)
    const p = getProject(get().currentProjectId)
    if (type === 'chat') {
      const chats = get().ensureProjectChats(get().currentProjectId)
      const primary = chats[0]
      get().ensureInstanceState(key, {
        ...syncPanelFromConversation(primary),
        model: DEFAULT_CHAT_MODEL,
        enabledTools: DEFAULT_CHAT_TOOLS,
        enabledMcps: DEFAULT_CHAT_MCPS,
        enabledSkills: DEFAULT_CHAT_SKILLS,
      })
    }
    if (type === 'code') {
      const first = p?.files[0]?.path || p?.files[0]?.name
      get().ensureInstanceState(key, {
        file: first,
        openFiles: first ? [first] : [],
        codeFontSize: 12,
        expandedFolders: defaultExpandedFolders(p?.files),
      })
    }
    const first = firstGroup(get().layout)
    if (first) {
      set({
        layout: addTabToGroup(get().layout, first.id, key),
      })
    }
    get().persist()
  },

  dropPanel: (panelId, groupId, edge) => {
    let layout: LayoutNode
    if (edge === 'center') {
      layout = addPanelToGroup(
        get().layout,
        groupId,
        panelId,
        true,
        () => get().nextGroupId(),
      )
    } else {
      layout = splitGroup(
        get().layout,
        groupId,
        panelId,
        edge,
        () => get().nextGroupId(),
      )
    }
    set({ layout, dragPanelId: null })
    get().persist()
  },

  movePanelToGroup: (panelId, groupId, insertIndex) => {
    const layout = movePanelToGroupAt(
      get().layout,
      groupId,
      panelId,
      insertIndex ?? Number.MAX_SAFE_INTEGER,
      () => get().nextGroupId(),
    )
    set({ layout, dragPanelId: null })
    get().persist()
  },

  resizeSplit: (pathToSplit, sizes) => {
    set({ layout: setSizesAtPath(get().layout, pathToSplit, sizes) })
    get().persist()
  },

  setActiveRepo: (repoId, projectId) => {
    const id = projectId || get().currentProjectId
    if (!id || !repoId) return
    const p = getProject(id)
    if (!p?.repos?.length) return
    if (!p.repos.some((r) => r.id === repoId)) return
    const repos = p.repos.map((r) => ({ ...r, active: r.id === repoId }))
    updateProjectInCatalog(id, { repos })
    set({
      activeRepoByProject: { ...get().activeRepoByProject, [id]: repoId },
      catalogVersion: get().catalogVersion + 1,
    })
    get().persist()
  },

  ensureProjectChats: (projectId) => {
    if (!projectId) return []
    const existing = get().projectChats[projectId]
    if (existing?.length) return existing
    const seeded = seedProjectConversations(projectId)
    set({
      projectChats: { ...get().projectChats, [projectId]: seeded },
    })
    return seeded
  },

  getConversations: (projectId) => {
    const id = projectId === undefined ? get().currentProjectId : projectId
    return sortConversations(get().ensureProjectChats(id))
  },

  getActiveConversation: (panelKey) => {
    const st = get().instanceState[panelKey]
    const projectId = get().currentProjectId
    if (!projectId || !st?.convId) return undefined
    const list = get().ensureProjectChats(projectId)
    return findConversation(list, st.convId)
  },

  updateConversationMessages: (projectId, convId, messages, lastAssistant) => {
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === convId)
    if (idx < 0) return
    let conv = { ...list[idx], messages: cloneMessages(messages) }
    conv = updateConvMetrics(conv, lastAssistant)
    list[idx] = conv
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
  },

  appendChatMessage: (panelKey, text) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const st = get().ensureInstanceState(panelKey, {
      model: DEFAULT_CHAT_MODEL,
      enabledTools: DEFAULT_CHAT_TOOLS,
      enabledMcps: DEFAULT_CHAT_MCPS,
      enabledSkills: DEFAULT_CHAT_SKILLS,
      enabledAgents: DEFAULT_CHAT_AGENTS,
      primaryAgent: DEFAULT_PRIMARY_AGENT,
      chatMode: DEFAULT_CHAT_MODE,
    })
    let convId = st.convId
    if (!convId) {
      const conv = emptyConversation(text.slice(0, 48) || 'New chat')
      const list = [...get().ensureProjectChats(projectId), conv]
      set({ projectChats: { ...get().projectChats, [projectId]: list } })
      convId = conv.id
      get().ensureInstanceState(panelKey, syncPanelFromConversation(conv))
    }

    const model = st.model || DEFAULT_CHAT_MODEL
    const tools = st.enabledTools || []
    const mode = (st.chatMode || DEFAULT_CHAT_MODE) as ChatMode
    const primaryAgent = st.primaryAgent || DEFAULT_PRIMARY_AGENT

    const userMsg: ChatMessage = {
      id: newMessageId('u'),
      role: 'user',
      text,
      blocks: [{ type: 'text', text }],
      createdAt: new Date().toISOString(),
    }
    const assistantMsgs = demoAssistantReply({
      userText: text,
      model,
      mode,
      tools,
      primaryAgent,
    })
    const messages = [...(st.messages || []), userMsg, ...assistantMsgs]
    const last = assistantMsgs[assistantMsgs.length - 1]
    get().updateConversationMessages(projectId, convId, messages, last)
    get().ensureInstanceState(panelKey, {
      convId,
      messages,
      title: st.title || deriveTitleFromMessages(messages),
    })
  },

  setChatConv: (panelKey, convId) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const list = get().ensureProjectChats(projectId)
    const conv = findConversation(list, convId)
    get().ensureInstanceState(panelKey, {
      ...syncPanelFromConversation(conv),
      model: get().instanceState[panelKey]?.model || DEFAULT_CHAT_MODEL,
      enabledTools: get().instanceState[panelKey]?.enabledTools || DEFAULT_CHAT_TOOLS,
      enabledMcps: get().instanceState[panelKey]?.enabledMcps || DEFAULT_CHAT_MCPS,
      enabledSkills: get().instanceState[panelKey]?.enabledSkills || DEFAULT_CHAT_SKILLS,
    })
  },

  newChatConversation: (panelKey) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const conv = emptyConversation()
    const list = [conv, ...get().ensureProjectChats(projectId)]
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
    get().ensureInstanceState(panelKey, {
      ...syncPanelFromConversation(conv),
      model: DEFAULT_CHAT_MODEL,
      enabledTools: DEFAULT_CHAT_TOOLS,
      enabledMcps: DEFAULT_CHAT_MCPS,
      enabledSkills: DEFAULT_CHAT_SKILLS,
    })
  },

  renameConversation: (projectId, convId, title) => {
    const trimmed = title.trim()
    if (!trimmed) return
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === convId)
    if (idx < 0) return
    list[idx] = { ...list[idx], title: trimmed }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
    // Sync open chat panels
    for (const [key, st] of Object.entries(get().instanceState)) {
      if (st.convId === convId) {
        get().ensureInstanceState(key as PanelKey, { title: trimmed })
      }
    }
  },

  deleteConversation: (projectId, convId, panelKey) => {
    let list = cloneConversations(get().ensureProjectChats(projectId)).filter(
      (c) => c.id !== convId,
    )
    if (list.length === 0) {
      list = [emptyConversation()]
    }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
    if (panelKey) {
      const st = get().instanceState[panelKey]
      if (st?.convId === convId) {
        get().ensureInstanceState(panelKey, syncPanelFromConversation(list[0]))
      }
    }
  },

  pinConversation: (projectId, convId, pinned) => {
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === convId)
    if (idx < 0) return
    list[idx] = {
      ...list[idx],
      pinned: pinned === undefined ? !list[idx].pinned : pinned,
    }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
  },

  aiTitleConversation: (projectId, convId) => {
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === convId)
    if (idx < 0) return
    const title = deriveTitleFromMessages(list[idx].messages)
    list[idx] = { ...list[idx], title, meta: 'AI titled · just now' }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
    for (const [key, st] of Object.entries(get().instanceState)) {
      if (st.convId === convId) {
        get().ensureInstanceState(key as PanelKey, { title })
      }
    }
  },

  forkConversation: (panelKey, fromMessageId) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const st = get().instanceState[panelKey]
    const src = get().getActiveConversation(panelKey)
    if (!src || !st) return
    const cutIdx = src.messages.findIndex((m) => m.id === fromMessageId)
    if (cutIdx < 0) return
    const forked = emptyConversation(`Fork: ${src.title}`)
    forked.messages = cloneMessages(src.messages.slice(0, cutIdx + 1))
    forked.agents = cloneConversations([src])[0].agents
    forked.primaryAgent = src.primaryAgent || DEFAULT_PRIMARY_AGENT
    forked.chatMode = src.chatMode
    forked.metrics = { ...src.metrics }
    forked.meta = 'Forked · just now'
    const list = [forked, ...get().ensureProjectChats(projectId)]
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
    get().ensureInstanceState(panelKey, syncPanelFromConversation(forked))
  },

  editUserMessage: (panelKey, messageId, text) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const st = get().ensureInstanceState(panelKey)
    const convId = st.convId
    if (!convId) return
    const msgs = cloneMessages(st.messages || [])
    const idx = msgs.findIndex((m) => m.id === messageId && m.role === 'user')
    if (idx < 0) return
    msgs[idx] = {
      ...msgs[idx],
      text,
      blocks: [{ type: 'text', text }],
    }
    // Truncate after this user message and re-run demo assistant
    const kept = msgs.slice(0, idx + 1)
    const mode = (st.chatMode || DEFAULT_CHAT_MODE) as ChatMode
    const assistantMsgs = demoAssistantReply({
      userText: text,
      model: st.model || DEFAULT_CHAT_MODEL,
      mode,
      tools: st.enabledTools || DEFAULT_CHAT_TOOLS,
      primaryAgent: st.primaryAgent || DEFAULT_PRIMARY_AGENT,
    })
    const next = [...kept, ...assistantMsgs]
    const last = assistantMsgs[assistantMsgs.length - 1]
    get().updateConversationMessages(projectId, convId, next, last)
    get().ensureInstanceState(panelKey, { messages: next })
  },

  retryAssistantMessage: (panelKey, messageId) => {
    const projectId = get().currentProjectId
    if (!projectId) return
    const st = get().ensureInstanceState(panelKey)
    const convId = st.convId
    if (!convId) return
    const msgs = cloneMessages(st.messages || [])
    const idx = msgs.findIndex((m) => m.id === messageId && m.role === 'assistant')
    if (idx < 0) return
    // Find preceding user message
    let userText = 'Retry'
    for (let i = idx - 1; i >= 0; i--) {
      if (msgs[i].role === 'user') {
        userText = msgs[i].text || msgs[i].blocks?.find((b) => b.text)?.text || userText
        break
      }
    }
    const kept = msgs.slice(0, idx)
    const assistantMsgs = demoAssistantReply({
      userText,
      model: st.model || DEFAULT_CHAT_MODEL,
      mode: (st.chatMode || DEFAULT_CHAT_MODE) as ChatMode,
      tools: st.enabledTools || DEFAULT_CHAT_TOOLS,
      primaryAgent: st.primaryAgent || DEFAULT_PRIMARY_AGENT,
      retry: true,
    })
    const next = [...kept, ...assistantMsgs]
    const last = assistantMsgs[assistantMsgs.length - 1]
    get().updateConversationMessages(projectId, convId, next, last)
    get().ensureInstanceState(panelKey, { messages: next })
  },

  setChatMode: (panelKey, mode) => {
    const projectId = get().currentProjectId
    get().ensureInstanceState(panelKey, { chatMode: mode })
    const st = get().instanceState[panelKey]
    if (!projectId || !st?.convId) return
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === st.convId)
    if (idx < 0) return
    list[idx] = { ...list[idx], chatMode: mode }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
  },

  setConversationAgents: (panelKey, agentIds) => {
    const projectId = get().currentProjectId
    const agents = agentIds.map((id) => agentById(id))
    get().ensureInstanceState(panelKey, { enabledAgents: agentIds })
    const st = get().instanceState[panelKey]
    if (!projectId || !st?.convId) return
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === st.convId)
    if (idx < 0) return
    list[idx] = { ...list[idx], agents }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
  },

  setConversationAgent: (panelKey, agentName) => {
    const projectId = get().currentProjectId
    const name = agentName.trim()
    if (!name) return
    get().ensureInstanceState(panelKey, { primaryAgent: name })
    const st = get().instanceState[panelKey]
    if (!projectId || !st?.convId) return
    const list = cloneConversations(get().ensureProjectChats(projectId))
    const idx = list.findIndex((c) => c.id === st.convId)
    if (idx < 0) return
    list[idx] = { ...list[idx], primaryAgent: name }
    set({ projectChats: { ...get().projectChats, [projectId]: list } })
  },

  setCodeFile: (panelKey, file) => {
    get().openCodeFile(panelKey, file)
  },

  openCodeFile: (panelKey, filePath) => {
    const st = get().instanceState[panelKey]
    const open = st?.openFiles ? [...st.openFiles] : []
    if (!open.includes(filePath)) open.push(filePath)
    get().ensureInstanceState(panelKey, { file: filePath, openFiles: open })
  },

  closeCodeFile: (panelKey, filePath) => {
    const st = get().instanceState[panelKey]
    const open = (st?.openFiles || []).filter((f) => f !== filePath)
    let active = st?.file
    if (active === filePath) {
      active = open[open.length - 1] || ''
    }
    get().ensureInstanceState(panelKey, {
      file: active,
      openFiles: open,
    })
  },

  setCodeFontSize: (panelKey, size) => {
    const clamped = Math.min(CODE_FONT_MAX, Math.max(CODE_FONT_MIN, Math.round(size)))
    get().ensureInstanceState(panelKey, { codeFontSize: clamped })
  },

  toggleCodeFolder: (panelKey, folderPath) => {
    const st = get().instanceState[panelKey]
    const cur = new Set(st?.expandedFolders || [])
    if (cur.has(folderPath)) cur.delete(folderPath)
    else cur.add(folderPath)
    get().ensureInstanceState(panelKey, { expandedFolders: [...cur] })
  },

  detachPanel: (panelId) => {
    const s = get()
    if (!s.currentProjectId) return
    const layout = removePanelFromLayout(s.layout, panelId, () => get().nextGroupId())
    const detached = new Set(s.detachedPanels)
    detached.add(panelId)
    set({ layout, detachedPanels: detached })
    get().persist()

    const url = new URL(window.location.href)
    url.searchParams.set('detach', panelId)
    url.searchParams.set('project', s.currentProjectId)
    const w = window.open(
      url.toString(),
      `everflow-${panelId.replace(/[^a-zA-Z0-9_-]/g, '_')}-${s.currentProjectId}`,
      'width=960,height=720,menubar=no,toolbar=no',
    )
    if (!w) {
      alert('Pop-up blocked — allow pop-ups to detach panels.')
      get().reattachPanel(panelId)
      return
    }
    const timer = window.setInterval(() => {
      if (w.closed) {
        window.clearInterval(timer)
        get().reattachPanel(panelId)
      }
    }, 500)
  },

  reattachPanel: (panelId) => {
    const s = get()
    const detached = new Set(s.detachedPanels)
    detached.delete(panelId)
    if (allPanelsInLayout(s.layout).includes(panelId)) {
      set({ detachedPanels: detached })
      return
    }
    const first = firstGroup(s.layout)
    let layout = s.layout
    if (first) {
      layout = addTabToGroup(s.layout, first.id, panelId)
    }
    set({ layout, detachedPanels: detached })
    get().persist()
  },
}))
