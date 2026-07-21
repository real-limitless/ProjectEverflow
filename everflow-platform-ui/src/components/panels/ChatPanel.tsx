import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import {
  DEFAULT_CHAT_AGENTS,
  DEFAULT_CHAT_MCPS,
  DEFAULT_CHAT_MODEL,
  DEFAULT_CHAT_MODE,
  DEFAULT_CHAT_SKILLS,
  DEFAULT_CHAT_TOOLS,
  type CatalogItem,
} from '@/data/chatCatalog'
import { getProject } from '@/data/projects'
import type { ChatConversation, ChatMessage, ChatMode, PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { isDemoMode } from '@/lib/api'
import {
  canUseOpenCode,
  createSession,
  deleteSession,
  ensureOpenCode,
  forkSession,
  listAgents,
  listMessages,
  listMcp,
  listProviders,
  listSessions,
  promptAsync,
  promptSync,
  respondPermission,
  revertMessage,
  subscribeEvents,
  updateSession,
} from '@/lib/opencode/client'
import { applyPartDelta, mapOcEvent, upsertMessage } from '@/lib/opencode/mapEvents'
import {
  mapOcMessages,
  mergeServerMessages,
  parseModelId,
  sessionToConversation,
} from '@/lib/opencode/mapParts'
import { ChatComposer } from './ChatComposer'
import { ChatEmptyState } from './ChatEmptyState'
import { ChatHeader } from './ChatHeader'
import { ChatMessageRow } from './ChatMessageRow'
import { ConnectProviderModal } from './ConnectProviderModal'
import { ConvRail } from './ConvRail'

interface ChatPanelProps {
  panelKey: PanelKey
}

type LiveStatus =
  | 'idle'
  | 'connecting'
  | 'ready'
  | 'needs_provider'
  | 'error'
  | 'demo'

export function ChatPanel({ panelKey }: ChatPanelProps) {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const instanceState = usePlaygroundStore((s) => s.instanceState[panelKey])
  const projectChats = usePlaygroundStore((s) => s.projectChats)
  const ensureInstanceState = usePlaygroundStore((s) => s.ensureInstanceState)
  const ensureProjectChats = usePlaygroundStore((s) => s.ensureProjectChats)
  const getConversations = usePlaygroundStore((s) => s.getConversations)
  const setChatConv = usePlaygroundStore((s) => s.setChatConv)
  const appendChatMessage = usePlaygroundStore((s) => s.appendChatMessage)
  const newChatConversation = usePlaygroundStore((s) => s.newChatConversation)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const renameConversation = usePlaygroundStore((s) => s.renameConversation)
  const deleteConversation = usePlaygroundStore((s) => s.deleteConversation)
  const pinConversation = usePlaygroundStore((s) => s.pinConversation)
  const aiTitleConversation = usePlaygroundStore((s) => s.aiTitleConversation)
  const forkConversation = usePlaygroundStore((s) => s.forkConversation)
  const editUserMessage = usePlaygroundStore((s) => s.editUserMessage)
  const retryAssistantMessage = usePlaygroundStore((s) => s.retryAssistantMessage)
  const setChatMode = usePlaygroundStore((s) => s.setChatMode)
  const setConversationAgents = usePlaygroundStore((s) => s.setConversationAgents)
  const updateConversationMessages = usePlaygroundStore((s) => s.updateConversationMessages)
  const [draft, setDraft] = useState('')
  const [liveStatus, setLiveStatus] = useState<LiveStatus>('idle')
  const [liveError, setLiveError] = useState<string | null>(null)
  const [providerOpen, setProviderOpen] = useState(false)
  const [models, setModels] = useState<CatalogItem[] | null>(null)
  const [mcpsLive, setMcpsLive] = useState<CatalogItem[] | null>(null)
  const [agentsLive, setAgentsLive] = useState<CatalogItem[] | null>(null)
  const [sending, setSending] = useState(false)
  const sseRef = useRef<AbortController | null>(null)
  const liveRef = useRef(false)
  const bootKeyRef = useRef<string | null>(null)
  const sendingRef = useRef(false)
  const pollAbortRef = useRef(0)

  const p = currentProjectId ? getProject(currentProjectId) : undefined
  const useLive = Boolean(
    currentProjectId && p && canUseOpenCode(p) && !isDemoMode(),
  )
  liveRef.current = useLive
  sendingRef.current = sending

  // Touch projectChats so component re-renders on conversation mutations
  void projectChats

  const conversations = useMemo(() => {
    if (!currentProjectId) return []
    ensureProjectChats(currentProjectId)
    return getConversations(currentProjectId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- projectChats drives refresh
  }, [currentProjectId, projectChats, ensureProjectChats, getConversations])

  const primary = conversations[0]
  const st =
    instanceState ||
    ensureInstanceState(panelKey, {
      convId: primary?.id,
      title: primary?.title,
      messages: primary ? JSON.parse(JSON.stringify(primary.messages)) : [],
      model: DEFAULT_CHAT_MODEL,
      enabledTools: DEFAULT_CHAT_TOOLS,
      enabledMcps: DEFAULT_CHAT_MCPS,
      enabledSkills: DEFAULT_CHAT_SKILLS,
      enabledAgents: DEFAULT_CHAT_AGENTS,
      chatMode: primary?.chatMode || DEFAULT_CHAT_MODE,
      railCollapsed: false,
    })

  const model = st.model || DEFAULT_CHAT_MODEL
  const tools = st.enabledTools || DEFAULT_CHAT_TOOLS
  const mcps = st.enabledMcps || DEFAULT_CHAT_MCPS
  const skills = st.enabledSkills || DEFAULT_CHAT_SKILLS
  const agents = st.enabledAgents || DEFAULT_CHAT_AGENTS
  const mode = (st.chatMode || DEFAULT_CHAT_MODE) as ChatMode
  const railCollapsed = !!st.railCollapsed
  const messages = st.messages || []
  const isEmpty = messages.length === 0

  const activeConv = conversations.find((c) => c.id === st.convId) || primary

  const hydrateSession = useCallback(
    async (
      projectId: string,
      sessionId: string,
      opts?: { allowEmpty?: boolean; force?: boolean },
    ) => {
      const allowEmpty = opts?.allowEmpty ?? false
      const force = opts?.force ?? false
      try {
        const bundles = await listMessages(projectId, sessionId)
        const serverMsgs = mapOcMessages(bundles)
        const local =
          usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
        const activeId =
          usePlaygroundStore.getState().instanceState[panelKey]?.convId

        // Don't apply a stale hydrate to a different session
        if (!force && activeId && activeId !== sessionId) {
          return local
        }

        // Never wipe non-empty local history with an empty server snapshot
        // (common while guest proxy is slow or mid-generation).
        // Session switch to a truly empty chat must pass allowEmpty: true.
        if (!allowEmpty && serverMsgs.length === 0 && local.length > 0) {
          return local
        }

        const msgs = mergeServerMessages(serverMsgs, local)
        const list = usePlaygroundStore.getState().ensureProjectChats(projectId)
        const conv = list.find((c) => c.id === sessionId)
        if (conv) {
          usePlaygroundStore
            .getState()
            .updateConversationMessages(projectId, sessionId, msgs)
        }
        ensureInstanceState(panelKey, {
          convId: sessionId,
          messages: msgs,
          title: conv?.title || usePlaygroundStore.getState().instanceState[panelKey]?.title,
        })
        return msgs
      } catch (e) {
        // Fetch failed — keep local messages, surface error
        setLiveError((e as Error).message)
        return usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
      }
    },
    [ensureInstanceState, panelKey],
  )

  const refreshSessions = useCallback(
    async (projectId: string, preferId?: string) => {
      const sessions = await listSessions(projectId)
      const prevList =
        usePlaygroundStore.getState().projectChats[projectId] || []
      const prevById = new Map(prevList.map((c) => [c.id, c]))

      const mapped: ChatConversation[] = []
      for (const s of sessions) {
        const prev = prevById.get(s.id)
        // Preserve in-memory messages for known sessions until hydrate fills them
        mapped.push(sessionToConversation(s, prev?.messages || []))
      }
      if (mapped.length === 0) {
        const created = await createSession(projectId, 'New chat')
        mapped.push(sessionToConversation(created, []))
      }
      usePlaygroundStore.setState((state) => ({
        projectChats: { ...state.projectChats, [projectId]: mapped },
      }))
      const pick =
        (preferId && mapped.find((c) => c.id === preferId)) ||
        mapped[0]
      if (pick) {
        // First load of a session may legitimately be empty
        const hadLocal = (prevById.get(pick.id)?.messages.length || 0) > 0
        await hydrateSession(projectId, pick.id, {
          allowEmpty: !hadLocal,
          force: true,
        })
      }
      return mapped
    },
    [hydrateSession],
  )

  const loadCatalogs = useCallback(async (projectId: string) => {
    try {
      const [prov, mcpMap, agentList] = await Promise.all([
        listProviders(projectId),
        listMcp(projectId).catch(() => ({})),
        listAgents(projectId).catch(() => []),
      ])
      const modelItems: CatalogItem[] = []
      for (const pvd of prov.providers || []) {
        const modelsRaw = pvd.models
        if (Array.isArray(modelsRaw)) {
          for (const m of modelsRaw) {
            modelItems.push({
              id: `${pvd.id}/${m.id}`,
              label: m.name || m.id,
              description: pvd.name || pvd.id,
            })
          }
        } else if (modelsRaw && typeof modelsRaw === 'object') {
          for (const [mid, meta] of Object.entries(modelsRaw)) {
            modelItems.push({
              id: `${pvd.id}/${mid}`,
              label: (meta as { name?: string })?.name || mid,
              description: pvd.name || pvd.id,
            })
          }
        }
      }
      setModels(modelItems.length ? modelItems : null)
      const connected = prov.connected || []
      if (connected.length === 0 && modelItems.length === 0) {
        // providers list may exist without connected
      }
      if (connected.length === 0) {
        // Still allow if user has no "connected" field — check later on send
        setLiveStatus((s) => (s === 'connecting' ? 'needs_provider' : s))
      }

      const mcpItems: CatalogItem[] = Object.entries(mcpMap || {}).map(([id, st]) => ({
        id,
        label: id,
        description:
          st && typeof st === 'object' && 'status' in st
            ? String((st as { status?: string }).status || 'MCP')
            : 'MCP',
      }))
      setMcpsLive(mcpItems.length ? mcpItems : null)

      const agentItems: CatalogItem[] = (agentList || []).map((a) => ({
        id: a.name,
        label: a.name,
        description: a.description || a.mode || 'agent',
      }))
      setAgentsLive(agentItems.length ? agentItems : null)

      return { connected, modelItems }
    } catch {
      return { connected: [] as string[], modelItems: [] as CatalogItem[] }
    }
  }, [])

  // Bootstrap OpenCode once per project when live (not on every sandboxStatus poll)
  useEffect(() => {
    if (!useLive || !currentProjectId) {
      setLiveStatus(isDemoMode() || !p?.fromApi ? 'demo' : 'idle')
      bootKeyRef.current = null
      return
    }
    const bootKey = `${currentProjectId}:live`
    if (bootKeyRef.current === bootKey) {
      return
    }
    bootKeyRef.current = bootKey

    let cancelled = false
    setLiveStatus('connecting')
    setLiveError(null)

    ;(async () => {
      try {
        await ensureOpenCode(currentProjectId)
        if (cancelled) return
        const cat = await loadCatalogs(currentProjectId)
        if (cancelled) return
        const prefer =
          usePlaygroundStore.getState().instanceState[panelKey]?.convId
        await refreshSessions(currentProjectId, prefer)
        if (cancelled) return

        // SSE (guest mode may only emit server.connected — we still poll on send)
        sseRef.current?.abort()
        sseRef.current = subscribeEvents(
          currentProjectId,
          (ev) => {
            if (!liveRef.current) return
            const patch = mapOcEvent(ev)
            const projectId = currentProjectId
            const convId = usePlaygroundStore.getState().instanceState[panelKey]?.convId
            if (!convId) return

            if (patch.kind === 'message') {
              const msgs =
                usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
              const next = upsertMessage(msgs, patch.message)
              usePlaygroundStore
                .getState()
                .updateConversationMessages(projectId, convId, next, patch.message)
              ensureInstanceState(panelKey, { messages: next })
            } else if (patch.kind === 'part_delta') {
              const msgs =
                usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
              const next = applyPartDelta(
                msgs,
                patch.messageId,
                patch.partType,
                patch.text,
              )
              usePlaygroundStore
                .getState()
                .updateConversationMessages(projectId, convId, next)
              ensureInstanceState(panelKey, { messages: next })
            } else if (patch.kind === 'permission') {
              const msgs =
                usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
              const permMsg: ChatMessage = {
                id: `perm-${patch.permissionId}`,
                role: 'assistant',
                blocks: [
                  {
                    type: 'permission',
                    permission: {
                      id: patch.permissionId,
                      title: patch.title,
                      detail: patch.detail,
                      status: 'pending',
                    },
                  },
                ],
              }
              const next = upsertMessage(msgs, permMsg)
              usePlaygroundStore
                .getState()
                .updateConversationMessages(projectId, convId, next)
              ensureInstanceState(panelKey, { messages: next })
            } else if (patch.kind === 'reload_messages') {
              void hydrateSession(projectId, convId)
            }
          },
          (err) => {
            console.warn('OpenCode SSE error', err)
          },
        )

        if (cat.connected.length === 0) {
          setLiveStatus('needs_provider')
        } else {
          setLiveStatus('ready')
        }
      } catch (e) {
        if (cancelled) return
        bootKeyRef.current = null
        setLiveError((e as Error).message)
        setLiveStatus('error')
      }
    })()

    return () => {
      cancelled = true
      sseRef.current?.abort()
      sseRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per project live session
  }, [useLive, currentProjectId])

  const sendLive = async (text: string) => {
    if (!currentProjectId || !st.convId) return
    const convId = st.convId
    const projectId = currentProjectId
    setSending(true)
    sendingRef.current = true
    setLiveError(null)
    const pollGen = ++pollAbortRef.current

    try {
      // Optimistic user + pending assistant placeholder
      const userMsg: ChatMessage = {
        id: `local-u-${Date.now()}`,
        role: 'user',
        text,
        blocks: [{ type: 'text', text }],
        createdAt: new Date().toISOString(),
      }
      const pendingAsst: ChatMessage = {
        id: `pending-a-${Date.now()}`,
        role: 'assistant',
        thinking: 'Working…',
        blocks: [{ type: 'markdown', text: '_Thinking…_' }],
      }
      const prev =
        usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
      const optimistic = [...prev, userMsg, pendingAsst]
      ensureInstanceState(panelKey, { messages: optimistic })
      updateConversationMessages(projectId, convId, optimistic)

      // Only pass model/agent when they come from live OpenCode catalogs
      const liveAgentIds = new Set((agentsLive || []).map((a) => a.id))
      const liveModelIds = new Set((models || []).map((m) => m.id))
      const modelRef =
        liveModelIds.has(model) || model.includes('/')
          ? parseModelId(model)
          : null
      const agentName =
        agents.find((id) => liveAgentIds.has(id)) ||
        (agentsLive && agentsLive[0]?.id) ||
        undefined

      const body: {
        parts: Array<{ type: string; text?: string }>
        model?: { providerID: string; modelID: string }
        agent?: string
      } = {
        parts: [{ type: 'text', text }],
      }
      if (modelRef) body.model = modelRef
      if (agentName) body.agent = agentName

      try {
        await promptAsync(projectId, convId, body)
      } catch (asyncErr) {
        try {
          await promptSync(projectId, convId, body)
        } catch (syncErr) {
          // Remove pending placeholder; keep user message
          const cur =
            usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
          const kept = cur.filter((m) => !m.id.startsWith('pending-'))
          ensureInstanceState(panelKey, { messages: kept })
          updateConversationMessages(projectId, convId, kept)
          throw syncErr || asyncErr
        }
      }

      // Poll until server has at least our user turn (and ideally assistant)
      const baseline = prev.length
      const deadline = Date.now() + 45_000
      let delay = 700
      while (Date.now() < deadline && pollAbortRef.current === pollGen) {
        await new Promise((r) => setTimeout(r, delay))
        if (pollAbortRef.current !== pollGen) break
        const msgs = await hydrateSession(projectId, convId)
        const hasUser = msgs.some(
          (m) => m.role === 'user' && (m.text || '').trim() === text.trim(),
        )
        const hasAsst =
          msgs.some((m) => m.role === 'assistant' && !m.id.startsWith('pending-')) &&
          msgs.length > baseline
        if (hasUser && hasAsst) break
        if (hasUser && msgs.length > baseline + 1) break
        delay = Math.min(delay * 1.35, 4000)
      }
    } catch (e) {
      setLiveError((e as Error).message)
      const msg = ((e as Error).message || '').toLowerCase()
      if (msg.includes('auth') || msg.includes('api key') || (e as { status?: number }).status === 401) {
        setLiveStatus('needs_provider')
      }
    } finally {
      if (pollAbortRef.current === pollGen) {
        setSending(false)
        sendingRef.current = false
        // Drop any leftover pending placeholder
        const cur =
          usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
        if (cur.some((m) => m.id.startsWith('pending-'))) {
          const cleaned = cur.filter((m) => !m.id.startsWith('pending-'))
          ensureInstanceState(panelKey, { messages: cleaned })
          updateConversationMessages(projectId, convId, cleaned)
        }
      }
    }
  }

  const send = (text?: string) => {
    const body = (text ?? draft).trim()
    if (!body) return
    setDraft('')
    if (useLive && (liveStatus === 'ready' || liveStatus === 'needs_provider')) {
      if (liveStatus === 'needs_provider') {
        setProviderOpen(true)
        setDraft(body)
        return
      }
      void sendLive(body)
      return
    }
    appendChatMessage(panelKey, body)
  }

  const onPermission = async (
    permissionId: string,
    response: 'once' | 'always' | 'reject',
  ) => {
    if (!useLive || !currentProjectId || !st.convId) return
    try {
      await respondPermission(
        currentProjectId,
        st.convId,
        permissionId,
        response,
        response === 'always',
      )
      const msgs = (st.messages || []).map((m) => {
        if (!m.blocks) return m
        return {
          ...m,
          blocks: m.blocks.map((b) =>
            b.type === 'permission' && b.permission?.id === permissionId
              ? {
                  ...b,
                  permission: { ...b.permission, status: 'resolved' as const },
                }
              : b,
          ),
        }
      })
      ensureInstanceState(panelKey, { messages: msgs })
      updateConversationMessages(currentProjectId, st.convId, msgs)
    } catch (e) {
      setLiveError((e as Error).message)
    }
  }

  const liveNewChat = async () => {
    if (!currentProjectId) return
    const created = await createSession(currentProjectId, 'New chat')
    await refreshSessions(currentProjectId, created.id)
  }

  const liveSelect = async (id: string) => {
    if (!currentProjectId) return
    // Switching sessions: allow empty history
    ensureInstanceState(panelKey, { convId: id, messages: [] })
    await hydrateSession(currentProjectId, id, { allowEmpty: true, force: true })
  }

  const liveRename = async (id: string, title: string) => {
    if (!currentProjectId) return
    await updateSession(currentProjectId, id, { title })
    renameConversation(currentProjectId, id, title)
  }

  const liveDelete = async (id: string) => {
    if (!currentProjectId) return
    await deleteSession(currentProjectId, id)
    await refreshSessions(currentProjectId)
  }

  const liveFork = async (messageId: string) => {
    if (!currentProjectId || !st.convId) return
    const forked = await forkSession(currentProjectId, st.convId, messageId)
    await refreshSessions(currentProjectId, forked.id)
  }

  const liveRetry = async (messageId: string) => {
    if (!currentProjectId || !st.convId) return
    await revertMessage(currentProjectId, st.convId, messageId)
    const msgs = st.messages || []
    const idx = msgs.findIndex((m) => m.id === messageId)
    let userText = ''
    for (let i = idx - 1; i >= 0; i--) {
      if (msgs[i].role === 'user') {
        userText = msgs[i].text || ''
        break
      }
    }
    if (userText) await sendLive(userText)
    else await hydrateSession(currentProjectId, st.convId)
  }

  const composerModels = models
  const composerMcps = mcpsLive ? mcpsLive.map((m) => m.id) : mcps
  const composerAgents = agentsLive ? agentsLive.map((a) => a.id) : agents

  return (
    <div
      className={`chat-layout${railCollapsed ? ' chat-layout--rail-collapsed' : ''}`}
      data-chat-instance={panelKey}
      data-opencode={useLive ? liveStatus : 'demo'}
    >
      {!railCollapsed ? (
        <ConvRail
          projectName={p?.name || 'Project'}
          conversations={conversations}
          activeConvId={st.convId}
          onSelect={(id) =>
            useLive ? void liveSelect(id) : setChatConv(panelKey, id)
          }
          onNewChat={() =>
            useLive ? void liveNewChat() : newChatConversation(panelKey)
          }
          onOpenPanel={() => openPanelType('chat')}
          onCollapse={() => ensureInstanceState(panelKey, { railCollapsed: true })}
          onPin={(id) => currentProjectId && pinConversation(currentProjectId, id)}
          onRename={(id, title) =>
            useLive
              ? void liveRename(id, title)
              : currentProjectId && renameConversation(currentProjectId, id, title)
          }
          onDelete={(id) =>
            useLive
              ? void liveDelete(id)
              : currentProjectId && deleteConversation(currentProjectId, id, panelKey)
          }
          onAiTitle={(id) =>
            currentProjectId && aiTitleConversation(currentProjectId, id)
          }
        />
      ) : null}

      {railCollapsed ? (
        <button
          type="button"
          className="conv-rail-expand"
          title="Show conversations"
          aria-label="Expand conversation list"
          onClick={() => ensureInstanceState(panelKey, { railCollapsed: false })}
        >
          <AngleRightIcon />
        </button>
      ) : null}

      <div className="chat-main">
        <ChatHeader
          title={st.title || activeConv?.title || 'Chat'}
          mode={mode}
          metrics={activeConv?.metrics}
          agents={activeConv?.agents}
          onModeChange={(m) => setChatMode(panelKey, m)}
        />

        {useLive && liveStatus === 'connecting' ? (
          <div className="chat-empty" style={{ minHeight: 80 }}>
            <p className="chat-empty-desc">Connecting to OpenCode in sandbox…</p>
          </div>
        ) : null}

        {useLive && liveStatus === 'error' ? (
          <div className="chat-empty" style={{ minHeight: 100 }}>
            <h2 className="chat-empty-title">OpenCode unavailable</h2>
            <p className="chat-empty-desc">{liveError || 'Unknown error'}</p>
            <button
              type="button"
              className="chat-empty-chip"
              onClick={() => {
                setLiveStatus('connecting')
                void ensureOpenCode(currentProjectId!, true)
                  .then(() => refreshSessions(currentProjectId!))
                  .then(() => loadCatalogs(currentProjectId!))
                  .then(() => setLiveStatus('ready'))
                  .catch((e) => {
                    setLiveError((e as Error).message)
                    setLiveStatus('error')
                  })
              }}
            >
              Retry
            </button>
          </div>
        ) : null}

        {useLive && liveStatus === 'needs_provider' ? (
          <div className="chat-empty" style={{ minHeight: 100 }}>
            <h2 className="chat-empty-title">Connect a provider</h2>
            <p className="chat-empty-desc">
              OpenCode needs an LLM API key in this sandbox before chat can run.
            </p>
            <button
              type="button"
              className="chat-empty-chip"
              onClick={() => setProviderOpen(true)}
            >
              Connect provider
            </button>
          </div>
        ) : null}

        <div className={`messages${isEmpty && !sending ? ' messages--empty' : ''}`}>
          {isEmpty && !sending && liveStatus !== 'connecting' && liveStatus !== 'error' ? (
            <ChatEmptyState
              onSuggestion={(text) => {
                setDraft(text)
              }}
            />
          ) : (
            messages.map((m, i) => (
              <ChatMessageRow
                key={m.id || `msg-${i}`}
                message={m}
                onEdit={(id, text) =>
                  useLive
                    ? void (async () => {
                        await revertMessage(currentProjectId!, st.convId!, id)
                        await sendLive(text)
                      })()
                    : editUserMessage(panelKey, id, text)
                }
                onRetry={(id) =>
                  useLive ? void liveRetry(id) : retryAssistantMessage(panelKey, id)
                }
                onFork={(id) =>
                  useLive ? void liveFork(id) : forkConversation(panelKey, id)
                }
                onQuestionOption={(opt) => send(opt)}
                onPermission={onPermission}
              />
            ))
          )}
        </div>

        {liveError && liveStatus === 'ready' ? (
          <div className="chat-composer-hint" role="alert" style={{ color: 'var(--pf-t--global--color--status--danger--default)' }}>
            {liveError}
          </div>
        ) : null}

        <ChatComposer
          draft={draft}
          onDraftChange={setDraft}
          onSend={() => send()}
          model={model}
          tools={tools}
          mcps={composerMcps}
          skills={skills}
          agents={composerAgents}
          mode={mode}
          onModelChange={(id) => ensureInstanceState(panelKey, { model: id })}
          onToolsChange={(ids) => ensureInstanceState(panelKey, { enabledTools: ids })}
          onMcpsChange={(ids) => ensureInstanceState(panelKey, { enabledMcps: ids })}
          onSkillsChange={(ids) =>
            ensureInstanceState(panelKey, { enabledSkills: ids })
          }
          onAgentsChange={(ids) => setConversationAgents(panelKey, ids)}
          modelOptions={composerModels || undefined}
          mcpOptions={mcpsLive || undefined}
          agentOptions={
            agentsLive
              ? agentsLive.map((a) => ({
                  id: a.id,
                  name: a.label,
                  role: 'general' as const,
                }))
              : undefined
          }
          sendDisabled={
            sending ||
            (useLive && (liveStatus === 'connecting' || liveStatus === 'error'))
          }
        />
      </div>

      {currentProjectId ? (
        <ConnectProviderModal
          projectId={currentProjectId}
          isOpen={providerOpen}
          onClose={() => setProviderOpen(false)}
          onConnected={() => {
            setLiveStatus('ready')
            void loadCatalogs(currentProjectId)
          }}
        />
      ) : null}
    </div>
  )
}
