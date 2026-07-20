import { useMemo, useState } from 'react'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import {
  DEFAULT_CHAT_AGENTS,
  DEFAULT_CHAT_MCPS,
  DEFAULT_CHAT_MODEL,
  DEFAULT_CHAT_MODE,
  DEFAULT_CHAT_SKILLS,
  DEFAULT_CHAT_TOOLS,
} from '@/data/chatCatalog'
import { PROJECTS } from '@/data/projects'
import type { ChatMode, PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { ChatComposer } from './ChatComposer'
import { ChatEmptyState } from './ChatEmptyState'
import { ChatHeader } from './ChatHeader'
import { ChatMessageRow } from './ChatMessageRow'
import { ConvRail } from './ConvRail'

interface ChatPanelProps {
  panelKey: PanelKey
}

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
  const [draft, setDraft] = useState('')

  const p = currentProjectId ? PROJECTS[currentProjectId] : undefined
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

  const send = (text?: string) => {
    const body = (text ?? draft).trim()
    if (!body) return
    appendChatMessage(panelKey, body)
    setDraft('')
  }

  return (
    <div
      className={`chat-layout${railCollapsed ? ' chat-layout--rail-collapsed' : ''}`}
      data-chat-instance={panelKey}
    >
      {!railCollapsed ? (
        <ConvRail
          projectName={p?.name || 'Project'}
          conversations={conversations}
          activeConvId={st.convId}
          onSelect={(id) => setChatConv(panelKey, id)}
          onNewChat={() => newChatConversation(panelKey)}
          onOpenPanel={() => openPanelType('chat')}
          onCollapse={() => ensureInstanceState(panelKey, { railCollapsed: true })}
          onPin={(id) => currentProjectId && pinConversation(currentProjectId, id)}
          onRename={(id, title) =>
            currentProjectId && renameConversation(currentProjectId, id, title)
          }
          onDelete={(id) =>
            currentProjectId && deleteConversation(currentProjectId, id, panelKey)
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

        <div className={`messages${isEmpty ? ' messages--empty' : ''}`}>
          {isEmpty ? (
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
                onEdit={(id, text) => editUserMessage(panelKey, id, text)}
                onRetry={(id) => retryAssistantMessage(panelKey, id)}
                onFork={(id) => forkConversation(panelKey, id)}
                onQuestionOption={(opt) => send(opt)}
              />
            ))
          )}
        </div>

        <ChatComposer
          draft={draft}
          onDraftChange={setDraft}
          onSend={() => send()}
          model={model}
          tools={tools}
          mcps={mcps}
          skills={skills}
          agents={agents}
          mode={mode}
          onModelChange={(id) => ensureInstanceState(panelKey, { model: id })}
          onToolsChange={(ids) => ensureInstanceState(panelKey, { enabledTools: ids })}
          onMcpsChange={(ids) => ensureInstanceState(panelKey, { enabledMcps: ids })}
          onSkillsChange={(ids) =>
            ensureInstanceState(panelKey, { enabledSkills: ids })
          }
          onAgentsChange={(ids) => setConversationAgents(panelKey, ids)}
        />
      </div>
    </div>
  )
}
