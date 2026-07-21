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
  listQuestions,
  listSessions,
  promptAsync,
  promptSync,
  rejectQuestion,
  respondPermission,
  respondQuestion,
  revertMessage,
  subscribeEvents,
  updateSession,
} from '@/lib/opencode/client'
import {
  applyPartDelta,
  applyPartFull,
  mapOcEvent,
  resolveQuestionMessage,
  upsertMessage,
  upsertQuestionMessage,
} from '@/lib/opencode/mapEvents'
import {
  assistantTurnReady,
  estimateLiveTokensPerSec,
  mapOcMessages,
  mergeServerMessages,
  messageHasReplyText,
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
  const [bootStage, setBootStage] = useState<string>('')
  const sseRef = useRef<AbortController | null>(null)
  const liveRef = useRef(false)
  /** Monotonic bootstrap generation — remount/retry increments; stale async exits. */
  const bootGenRef = useRef(0)
  const sendingRef = useRef(false)
  const pollAbortRef = useRef(0)
  /** Question request ids already answered in this session — never re-inject as pending. */
  const answeredQuestionIdsRef = useRef<Set<string>>(new Set())

  function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const t = window.setTimeout(() => {
        reject(new Error(`${label} timed out after ${Math.round(ms / 1000)}s`))
      }, ms)
      p.then(
        (v) => {
          window.clearTimeout(t)
          resolve(v)
        },
        (e) => {
          window.clearTimeout(t)
          reject(e)
        },
      )
    })
  }

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
      opts?: {
        allowEmpty?: boolean
        force?: boolean
        clientTtftMs?: number
        streamStartedAt?: number
      },
    ) => {
      const allowEmpty = opts?.allowEmpty ?? false
      const force = opts?.force ?? false
      try {
        const bundles = await listMessages(projectId, sessionId)
        let serverMsgs = mapOcMessages(bundles, {
          clientTtftMs: opts?.clientTtftMs,
        })
        // Live tok/s while streaming when OpenCode hasn't finished yet
        if (opts?.streamStartedAt) {
          const elapsed = Date.now() - opts.streamStartedAt
          serverMsgs = serverMsgs.map((m) => {
            if (m.role !== 'assistant' || m.generationStatus === 'complete') return m
            const live = estimateLiveTokensPerSec(m, elapsed)
            if (live == null) return m
            return {
              ...m,
              metrics: {
                ...m.metrics,
                tokensPerSec: m.metrics?.tokensPerSec ?? live,
                ttftMs: m.metrics?.ttftMs ?? opts.clientTtftMs,
              },
            }
          })
        }

        // Merge pending OpenCode questions (SSE may have been missed).
        // Never re-inject ids the user already answered in this tab.
        try {
          const pendingQs = await listQuestions(projectId)
          for (const q of pendingQs) {
            if (q.sessionID && q.sessionID !== sessionId) continue
            if (!q.id || !Array.isArray(q.questions) || !q.questions.length) continue
            if (answeredQuestionIdsRef.current.has(q.id)) continue
            serverMsgs = upsertQuestionMessage(serverMsgs, {
              requestId: q.id,
              questions: q.questions,
              messageId: q.tool?.messageID,
            })
          }
        } catch {
          /* optional */
        }

        const local =
          usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
        const activeId =
          usePlaygroundStore.getState().instanceState[panelKey]?.convId

        // Don't apply a stale hydrate to a different session
        if (!force && activeId && activeId !== sessionId) {
          return local
        }

        // Never wipe non-empty local history with an empty server snapshot
        if (!allowEmpty && serverMsgs.length === 0 && local.length > 0) {
          return local
        }

        // Preserve local pending question cards if server list lags;
        // also re-apply local "answered" status so hydrate does not reopen chips.
        let msgs = mergeServerMessages(serverMsgs, local)
        for (const m of local) {
          for (const b of m.blocks || []) {
            if (b.type !== 'question' || !b.questionRequest?.id) continue
            const qid = b.questionRequest.id
            if (
              b.questionRequest.status === 'answered' ||
              b.questionRequest.status === 'rejected' ||
              answeredQuestionIdsRef.current.has(qid)
            ) {
              answeredQuestionIdsRef.current.add(qid)
              msgs = resolveQuestionMessage(
                msgs,
                qid,
                b.questionRequest.status === 'rejected' ? 'rejected' : 'answered',
              )
              continue
            }
            if (b.questionRequest.status === 'pending') {
              const already = msgs.some((sm) =>
                (sm.blocks || []).some(
                  (sb) =>
                    sb.type === 'question' && sb.questionRequest?.id === qid,
                ),
              )
              if (!already && !answeredQuestionIdsRef.current.has(qid)) {
                msgs = upsertQuestionMessage(msgs, {
                  requestId: qid,
                  questions: b.questionRequest.items.map((it) => ({
                    question: it.question,
                    header: it.header,
                    options: it.options,
                    multiple: it.multiple,
                    custom: it.custom,
                  })),
                })
              }
            }
          }
        }
        const lastAsst = [...msgs]
          .reverse()
          .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
        const list = usePlaygroundStore.getState().ensureProjectChats(projectId)
        const conv = list.find((c) => c.id === sessionId)
        if (conv) {
          usePlaygroundStore
            .getState()
            .updateConversationMessages(projectId, sessionId, msgs, lastAsst)
        }
        ensureInstanceState(panelKey, {
          convId: sessionId,
          messages: msgs,
          title:
            conv?.title ||
            usePlaygroundStore.getState().instanceState[panelKey]?.title,
        })
        return msgs
      } catch (e) {
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

  // Bootstrap OpenCode when live. Generation token survives Strict Mode remounts:
  // cleanup cancels the prior gen; a new effect always starts a fresh bootstrap.
  useEffect(() => {
    if (!useLive || !currentProjectId) {
      setLiveStatus(isDemoMode() || !p?.fromApi ? 'demo' : 'idle')
      setBootStage('')
      return
    }

    let cancelled = false
    const gen = ++bootGenRef.current
    setLiveStatus('connecting')
    setLiveError(null)
    setBootStage('Starting OpenCode in sandbox…')

    const stillActive = () => !cancelled && gen === bootGenRef.current

    ;(async () => {
      try {
        setBootStage('Starting OpenCode in sandbox…')
        await withTimeout(ensureOpenCode(currentProjectId), 25_000, 'OpenCode ensure')
        if (!stillActive()) return

        setBootStage('Loading providers…')
        let cat = { connected: [] as string[], modelItems: [] as CatalogItem[] }
        try {
          cat = await withTimeout(loadCatalogs(currentProjectId), 20_000, 'Provider catalog')
        } catch (catErr) {
          // Non-fatal: chat can still open; user may connect provider later
          console.warn('OpenCode catalog load failed', catErr)
        }
        if (!stillActive()) return

        setBootStage('Loading sessions…')
        const prefer =
          usePlaygroundStore.getState().instanceState[panelKey]?.convId
        try {
          await withTimeout(refreshSessions(currentProjectId, prefer), 25_000, 'Session list')
        } catch (sessErr) {
          // Soft-fail: create a local empty slot so user can still try send
          console.warn('OpenCode session refresh failed', sessErr)
          setLiveError((sessErr as Error).message)
          try {
            const created = await withTimeout(
              createSession(currentProjectId, 'New chat'),
              15_000,
              'Create session',
            )
            if (stillActive()) {
              ensureInstanceState(panelKey, {
                convId: created.id,
                title: created.title || 'New chat',
                messages: [],
              })
            }
          } catch {
            /* ignore — send path can create later */
          }
        }
        if (!stillActive()) return

        // Primary token stream: OpenCode /event bridged through agent (guest SSE)
        const attachSse = () => {
          sseRef.current?.abort()
          sseRef.current = subscribeEvents(
            currentProjectId,
            (ev) => {
              if (!liveRef.current) return
              const patch = mapOcEvent(ev)
              const projectId = currentProjectId
              const convId =
                usePlaygroundStore.getState().instanceState[panelKey]?.convId
              if (!convId) return

              const apply = (next: ChatMessage[], last?: ChatMessage) => {
                usePlaygroundStore
                  .getState()
                  .updateConversationMessages(projectId, convId, next, last)
                ensureInstanceState(panelKey, { messages: next })
              }

              if (patch.kind === 'message') {
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
                const next = upsertMessage(msgs, patch.message)
                apply(next, patch.message)
              } else if (patch.kind === 'part_delta' || patch.kind === 'part_set') {
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
                const next = applyPartDelta(
                  msgs,
                  patch.messageId,
                  patch.partType,
                  patch.text,
                  patch.kind === 'part_set' ? 'set' : 'append',
                )
                const last = next.find((m) => m.id === patch.messageId)
                apply(next, last)
              } else if (patch.kind === 'part_full') {
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
                const next = applyPartFull(msgs, patch.messageId, patch.part)
                const last = next.find((m) => m.id === patch.messageId)
                apply(next, last)
              } else if (patch.kind === 'question') {
                // Only show for the active session (or unknown session id)
                if (
                  patch.sessionId &&
                  patch.sessionId !== convId &&
                  patch.sessionId.length > 0
                ) {
                  return
                }
                // Ignore late SSE for a question we already answered
                if (answeredQuestionIdsRef.current.has(patch.requestId)) {
                  return
                }
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
                const next = upsertQuestionMessage(msgs, {
                  requestId: patch.requestId,
                  questions: patch.questions,
                  messageId: patch.messageId,
                })
                apply(next)
              } else if (patch.kind === 'question_resolved') {
                if (
                  patch.sessionId &&
                  patch.sessionId !== convId &&
                  patch.sessionId.length > 0
                ) {
                  return
                }
                answeredQuestionIdsRef.current.add(patch.requestId)
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
                apply(resolveQuestionMessage(msgs, patch.requestId, patch.status))
                // Agent continues after answer — refresh history
                void hydrateSession(projectId, convId, { force: true })
              } else if (patch.kind === 'permission') {
                if (
                  patch.sessionId &&
                  patch.sessionId !== convId &&
                  patch.sessionId.length > 0
                ) {
                  return
                }
                const msgs =
                  usePlaygroundStore.getState().instanceState[panelKey]?.messages ||
                  []
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
                apply(upsertMessage(msgs, permMsg))
              } else if (patch.kind === 'reload_messages') {
                void hydrateSession(projectId, convId, { force: true })
              }
            },
            (err) => {
              console.warn('OpenCode SSE error', err)
              // Soft reconnect after brief delay
              window.setTimeout(() => {
                if (liveRef.current && currentProjectId) attachSse()
              }, 1500)
            },
          )
        }
        attachSse()

        if (!stillActive()) return
        setBootStage('')
        if (cat.connected.length === 0) {
          setLiveStatus('needs_provider')
        } else {
          setLiveStatus('ready')
        }
      } catch (e) {
        if (!stillActive()) return
        setBootStage('')
        setLiveError((e as Error).message)
        setLiveStatus('error')
      }
    })()

    return () => {
      cancelled = true
      // Invalidate this generation so a remount always reboots
      if (bootGenRef.current === gen) {
        bootGenRef.current += 1
      }
      sseRef.current?.abort()
      sseRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- live project connection only
  }, [useLive, currentProjectId])

  const sendLive = async (text: string) => {
    if (!currentProjectId || !st.convId) return
    const convId = st.convId
    const projectId = currentProjectId
    setSending(true)
    sendingRef.current = true
    setLiveError(null)
    const pollGen = ++pollAbortRef.current
    const streamStartedAt = Date.now()
    let clientTtftMs: number | undefined

    try {
      // Optimistic user + pending assistant (spinner only — no fake markdown)
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
        generationStatus: 'incomplete',
      }
      const prev =
        usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
      const optimistic = [...prev, userMsg, pendingAsst]
      ensureInstanceState(panelKey, { messages: optimistic })
      updateConversationMessages(projectId, convId, optimistic)

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
          const cur =
            usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
          const kept = cur.filter((m) => !m.id.startsWith('pending-'))
          ensureInstanceState(panelKey, { messages: kept })
          updateConversationMessages(projectId, convId, kept)
          throw syncErr || asyncErr
        }
      }

      // SSE is primary (guest stream_exec → /event). Poll is a slow backup only.
      const deadline = Date.now() + 180_000
      const pollMs = 2000
      let gotReady = false
      while (Date.now() < deadline && pollAbortRef.current === pollGen) {
        await new Promise((r) => setTimeout(r, pollMs))
        if (pollAbortRef.current !== pollGen) break
        // Prefer in-memory stream state (updated by SSE handlers)
        let msgs =
          usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
        let lastAsst = [...msgs]
          .reverse()
          .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
        if (
          clientTtftMs == null &&
          lastAsst &&
          (messageHasReplyText(lastAsst) || !!(lastAsst.thinking || '').trim())
        ) {
          clientTtftMs = Date.now() - streamStartedAt
        }
        if (assistantTurnReady(lastAsst)) {
          gotReady = true
          break
        }
        // Backup hydrate if SSE silent / incomplete
        msgs = await hydrateSession(projectId, convId, {
          force: true,
          clientTtftMs,
          streamStartedAt,
        })
        lastAsst = [...msgs]
          .reverse()
          .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
        if (
          clientTtftMs == null &&
          lastAsst &&
          (messageHasReplyText(lastAsst) || !!(lastAsst.thinking || '').trim())
        ) {
          clientTtftMs = Date.now() - streamStartedAt
        }
        if (assistantTurnReady(lastAsst)) {
          gotReady = true
          break
        }
      }

      if (pollAbortRef.current === pollGen) {
        const finalMsgs = await hydrateSession(projectId, convId, {
          force: true,
          clientTtftMs,
          streamStartedAt,
        })
        const lastAsst = [...finalMsgs]
          .reverse()
          .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
        if (assistantTurnReady(lastAsst) || messageHasReplyText(lastAsst!)) {
          gotReady = true
          setLiveError(null)
        } else if (!gotReady) {
          setLiveError(
            'No complete response from OpenCode yet. The answer may still appear if you refresh.',
          )
        }
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
        const cur =
          usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
        const lastAsst = [...cur]
          .reverse()
          .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
        if (cur.some((m) => m.id.startsWith('pending-')) && assistantTurnReady(lastAsst)) {
          const cleaned = cur.filter((m) => !m.id.startsWith('pending-'))
          ensureInstanceState(panelKey, { messages: cleaned })
          updateConversationMessages(projectId, convId, cleaned, lastAsst)
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

  const onQuestionReply = async (requestId: string, answers: string[][]) => {
    if (!requestId) {
      setLiveError('Missing question request id — try refreshing the chat.')
      return
    }
    if (!useLive || !currentProjectId || !st.convId) {
      // Demo / offline: fall back to sending the first label as a user message
      const label = answers.flat().filter(Boolean)[0]
      if (label) send(label)
      return
    }
    const projectId = currentProjectId
    const convId = st.convId

    // Optimistic: lock the card immediately so the UI never looks stuck
    answeredQuestionIdsRef.current.add(requestId)
    const optimistic = resolveQuestionMessage(
      usePlaygroundStore.getState().instanceState[panelKey]?.messages || [],
      requestId,
      'answered',
    )
    ensureInstanceState(panelKey, { messages: optimistic })
    updateConversationMessages(projectId, convId, optimistic)
    setLiveError(null)
    setSending(true)
    sendingRef.current = true

    try {
      await respondQuestion(projectId, requestId, answers, convId)
      // Resume polling for the continued assistant turn after the tool unblocks
      const pollGen = ++pollAbortRef.current
      const streamStartedAt = Date.now()
      ;(async () => {
        const deadline = Date.now() + 180_000
        try {
          // Immediate hydrate so tool completion shows up quickly
          await hydrateSession(projectId, convId, {
            force: true,
            streamStartedAt,
          })
          while (Date.now() < deadline && pollAbortRef.current === pollGen) {
            await new Promise((r) => setTimeout(r, 1200))
            if (pollAbortRef.current !== pollGen) break
            const hydrated = await hydrateSession(projectId, convId, {
              force: true,
              streamStartedAt,
            })
            const lastAsst = [...hydrated]
              .reverse()
              .find((m) => m.role === 'assistant' && !m.id.startsWith('pending-'))
            if (assistantTurnReady(lastAsst)) break
          }
        } finally {
          if (pollAbortRef.current === pollGen) {
            setSending(false)
            sendingRef.current = false
          }
        }
      })()
    } catch (e) {
      // Re-open the question so the user can retry
      answeredQuestionIdsRef.current.delete(requestId)
      const reopened = (
        usePlaygroundStore.getState().instanceState[panelKey]?.messages || []
      ).map((m) => {
        if (!m.blocks) return m
        return {
          ...m,
          blocks: m.blocks.map((b) =>
            b.type === 'question' && b.questionRequest?.id === requestId
              ? {
                  ...b,
                  questionRequest: {
                    ...b.questionRequest,
                    status: 'pending' as const,
                  },
                }
              : b,
          ),
        }
      })
      ensureInstanceState(panelKey, { messages: reopened })
      updateConversationMessages(projectId, convId, reopened)
      setSending(false)
      sendingRef.current = false
      const detail = (e as Error).message || 'Failed to submit answer'
      setLiveError(`Could not submit answer: ${detail}`)
    }
  }

  const onQuestionReject = async (requestId: string) => {
    if (!useLive || !currentProjectId || !st.convId) return
    const projectId = currentProjectId
    const convId = st.convId
    answeredQuestionIdsRef.current.add(requestId)
    const optimistic = resolveQuestionMessage(
      usePlaygroundStore.getState().instanceState[panelKey]?.messages || [],
      requestId,
      'rejected',
    )
    ensureInstanceState(panelKey, { messages: optimistic })
    updateConversationMessages(projectId, convId, optimistic)
    try {
      await rejectQuestion(projectId, requestId, convId)
    } catch (e) {
      answeredQuestionIdsRef.current.delete(requestId)
      setLiveError(`Could not dismiss question: ${(e as Error).message}`)
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
            <p className="chat-empty-desc">
              {bootStage || 'Connecting to OpenCode in sandbox…'}
            </p>
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
                // Force effect re-run by bumping generation and toggling status
                bootGenRef.current += 1
                setLiveError(null)
                setBootStage('Retrying…')
                setLiveStatus('connecting')
                const projectId = currentProjectId!
                const gen = bootGenRef.current
                ;(async () => {
                  try {
                    await withTimeout(ensureOpenCode(projectId, true), 25_000, 'OpenCode ensure')
                    if (gen !== bootGenRef.current) return
                    const cat = await withTimeout(
                      loadCatalogs(projectId),
                      20_000,
                      'Provider catalog',
                    ).catch(() => ({ connected: [] as string[], modelItems: [] as CatalogItem[] }))
                    if (gen !== bootGenRef.current) return
                    await withTimeout(refreshSessions(projectId), 25_000, 'Session list').catch(
                      () => undefined,
                    )
                    if (gen !== bootGenRef.current) return
                    setBootStage('')
                    setLiveStatus(cat.connected.length === 0 ? 'needs_provider' : 'ready')
                  } catch (e) {
                    if (gen !== bootGenRef.current) return
                    setBootStage('')
                    setLiveError((e as Error).message)
                    setLiveStatus('error')
                  }
                })()
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
                onQuestionReply={(requestId, answers) =>
                  void onQuestionReply(requestId, answers)
                }
                onQuestionReject={(requestId) => void onQuestionReject(requestId)}
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
