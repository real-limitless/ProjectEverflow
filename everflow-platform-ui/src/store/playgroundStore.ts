import { create } from 'zustand'
import { PANEL_META } from '@/data/panelMeta'
import { PROJECTS } from '@/data/projects'
import {
  addPanelToGroup,
  addTabToGroup,
  allPanelsInLayout,
  cloneLayout,
  countTypeInLayout,
  firstGroup,
  removePanelFromLayout,
  setActiveTab,
  setSizesAtPath,
  splitGroup,
} from '@/lib/dockTree'
import { loadPersisted, savePersisted } from '@/lib/layoutPersist'
import { typeOf } from '@/lib/panelIds'
import type { DropEdge, LayoutNode } from '@/types/dock'
import type { PanelInstanceState, PanelKey, PanelType } from '@/types/panels'
import type { PaletteMode } from '@/types/project'

interface PlaygroundState {
  openProjectIds: string[]
  currentProjectId: string
  layout: LayoutNode
  projectLayouts: Record<string, LayoutNode>
  instanceState: Record<string, PanelInstanceState>
  groupIdSeq: number
  instanceSeq: number
  sidebarCollapsed: boolean
  isSidebarOpen: boolean
  paletteMode: PaletteMode
  palettePos: { x: number; y: number }
  paletteVisible: boolean
  openProjectModal: boolean
  connectRepoModal: boolean
  dragPanelId: string | null
  detachedPanels: Set<string>

  // derived helpers exposed as methods
  nextGroupId: () => string
  spawnPanelKey: (type: PanelType, opts?: Partial<PanelInstanceState>) => PanelKey
  ensureInstanceState: (key: PanelKey, opts?: Partial<PanelInstanceState>) => PanelInstanceState
  panelTabLabel: (key: PanelKey) => string
  getLayout: () => LayoutNode
  setLayout: (layout: LayoutNode) => void
  persist: () => void

  setSidebarCollapsed: (v: boolean) => void
  setSidebarOpen: (v: boolean) => void
  setPaletteMode: (mode: PaletteMode) => void
  setPalettePos: (pos: { x: number; y: number }) => void
  setPaletteVisible: (v: boolean) => void
  setOpenProjectModal: (v: boolean) => void
  setConnectRepoModal: (v: boolean) => void
  setDragPanelId: (id: string | null) => void

  switchProject: (id: string) => void
  openProject: (id: string) => void
  closeProjectTab: (id: string) => void
  resetLayout: () => void

  activateTab: (groupId: string, panelId: PanelKey) => void
  closePanel: (panelId: PanelKey) => void
  duplicatePanel: (groupId: string, panelId: PanelKey) => void
  openPanelType: (type: PanelType) => void
  dropPanel: (panelId: PanelKey, groupId: string, edge: DropEdge) => void
  resizeSplit: (pathToSplit: number[], sizes: number[]) => void
  setActiveRepo: (repoId: string) => void
  appendChatMessage: (panelKey: PanelKey, text: string) => void
  setChatConv: (panelKey: PanelKey, convId: string) => void
  setCodeFile: (panelKey: PanelKey, file: string) => void
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

function buildDefaultLayout(
  nextGroupId: () => string,
  spawn: (type: PanelType, opts?: Partial<PanelInstanceState>) => PanelKey,
  ensure: (key: PanelKey, opts?: Partial<PanelInstanceState>) => void,
  projectId: string,
): LayoutNode {
  const keys = seedInstances((t) => {
    const k = spawn(t)
    ensure(k)
    return k
  })
  // seed chat with project messages
  const p = PROJECTS[projectId]
  if (p) {
    ensure(keys.chat, {
      convId: p.convs[0]?.id,
      title: p.convs[0]?.title,
      messages: JSON.parse(JSON.stringify(p.messages)) as PanelInstanceState['messages'],
    })
    ensure(keys.code, { file: p.files[0]?.name })
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

function createInitial() {
  let groupIdSeq = 1
  let instanceSeq = 1
  const instanceState: Record<string, PanelInstanceState> = {}

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

  const openProjectIds = ['aura', 'callour']
  const currentProjectId = 'aura'
  const projectLayouts: Record<string, LayoutNode> = {}
  const layout = buildDefaultLayout(
    nextGroupId,
    spawnPanelKey,
    ensureInstanceState,
    currentProjectId,
  )
  projectLayouts[currentProjectId] = cloneLayout(layout)

  const persisted = loadPersisted()
  if (persisted) {
    const ids = (persisted.openProjectIds || openProjectIds).filter((id) => PROJECTS[id])
    return {
      openProjectIds: ids.length ? ids : openProjectIds,
      currentProjectId: PROJECTS[persisted.currentProjectId]
        ? persisted.currentProjectId
        : ids[0] || currentProjectId,
      layout: persisted.projectLayouts[persisted.currentProjectId]
        ? cloneLayout(persisted.projectLayouts[persisted.currentProjectId])
        : layout,
      projectLayouts: persisted.projectLayouts,
      instanceState: persisted.instanceState || instanceState,
      groupIdSeq: persisted.groupIdSeq || groupIdSeq,
      instanceSeq: persisted.instanceSeq || instanceSeq,
      paletteMode: persisted.paletteMode || ('float' as PaletteMode),
      palettePos: persisted.palettePos || { x: 24, y: window.innerHeight - 160 },
    }
  }

  return {
    openProjectIds,
    currentProjectId,
    layout,
    projectLayouts,
    instanceState,
    groupIdSeq,
    instanceSeq,
    paletteMode: 'float' as PaletteMode,
    palettePos: { x: 24, y: typeof window !== 'undefined' ? window.innerHeight - 160 : 600 },
  }
}

const initial = createInitial()

export const usePlaygroundStore = create<PlaygroundState>((set, get) => ({
  ...initial,
  sidebarCollapsed: false,
  isSidebarOpen: true,
  paletteVisible: true,
  openProjectModal: false,
  connectRepoModal: false,
  dragPanelId: null,
  detachedPanels: new Set(),

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
    const projectLayouts = {
      ...s.projectLayouts,
      [s.currentProjectId]: cloneLayout(s.layout),
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
  setConnectRepoModal: (v) => set({ connectRepoModal: v }),
  setDragPanelId: (id) => set({ dragPanelId: id }),

  switchProject: (id) => {
    if (!PROJECTS[id]) return
    const s = get()
    if (id === s.currentProjectId) return
    const projectLayouts = {
      ...s.projectLayouts,
      [s.currentProjectId]: cloneLayout(s.layout),
    }
    let layout = projectLayouts[id]
    if (!layout) {
      layout = buildDefaultLayout(
        () => get().nextGroupId(),
        (t, o) => get().spawnPanelKey(t, o),
        (k, o) => {
          get().ensureInstanceState(k, o)
        },
        id,
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
    set({ openProjectModal: false })
  },

  closeProjectTab: (id) => {
    const s = get()
    if (s.openProjectIds.length <= 1) return
    const openProjectIds = s.openProjectIds.filter((x) => x !== id)
    if (s.currentProjectId === id) {
      const next = openProjectIds[0]
      set({ openProjectIds })
      get().switchProject(next)
    } else {
      set({ openProjectIds })
      get().persist()
    }
  },

  resetLayout: () => {
    const id = get().currentProjectId
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
    get().persist()
  },

  duplicatePanel: (groupId, panelId) => {
    const type = typeOf(panelId) as PanelType
    if (!type) return
    const opts: Partial<PanelInstanceState> = {}
    if (type === 'chat') {
      opts.convId = `n${Date.now()}`
      opts.title = 'New chat'
      opts.messages = []
    }
    const key = get().spawnPanelKey(type, opts)
    const layout = addTabToGroup(get().layout, groupId, key)
    set({ layout })
    get().persist()
  },

  openPanelType: (type) => {
    const key = get().spawnPanelKey(type)
    get().ensureInstanceState(key)
    if (type === 'chat') {
      const p = PROJECTS[get().currentProjectId]
      get().ensureInstanceState(key, {
        convId: p?.convs[0]?.id,
        title: p?.convs[0]?.title || 'Chat',
        messages: p ? JSON.parse(JSON.stringify(p.messages)) : [],
      })
    }
    if (type === 'code') {
      const p = PROJECTS[get().currentProjectId]
      get().ensureInstanceState(key, { file: p?.files[0]?.name })
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

  resizeSplit: (pathToSplit, sizes) => {
    set({ layout: setSizesAtPath(get().layout, pathToSplit, sizes) })
    get().persist()
  },

  setActiveRepo: (repoId) => {
    // Demo: repos live in static PROJECTS — mutate local copy in memory only via layout n/a
    // For demo we keep repos in PROJECTS as shared; use a light override map if needed.
    void repoId
  },

  appendChatMessage: (panelKey, text) => {
    const st = get().ensureInstanceState(panelKey)
    const messages = [
      ...(st.messages || []),
      { role: 'user' as const, text },
      {
        role: 'assistant' as const,
        text: 'Demo reply — wire to AI workspace later. I noted your request and would apply changes in the sandbox.',
        thinking: 'Demo mode: no backend LLM connected.',
      },
    ]
    get().ensureInstanceState(panelKey, { messages })
  },

  setChatConv: (panelKey, convId) => {
    const p = PROJECTS[get().currentProjectId]
    const conv = p?.convs.find((c) => c.id === convId)
    const isPrimary = conv && p?.convs[0] && conv.id === p.convs[0].id
    get().ensureInstanceState(panelKey, {
      convId,
      title: conv?.title || 'Chat',
      messages:
        isPrimary && p
          ? (JSON.parse(JSON.stringify(p.messages)) as PanelInstanceState['messages'])
          : [],
    })
  },

  setCodeFile: (panelKey, file) => {
    get().ensureInstanceState(panelKey, { file })
  },

  detachPanel: (panelId) => {
    const s = get()
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
