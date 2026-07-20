import { useState } from 'react'
import { Button } from '@patternfly/react-core'
import AngleLeftIcon from '@patternfly/react-icons/dist/esm/icons/angle-left-icon'
import AngleRightIcon from '@patternfly/react-icons/dist/esm/icons/angle-right-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import {
  DEFAULT_CHAT_MCPS,
  DEFAULT_CHAT_MODEL,
  DEFAULT_CHAT_SKILLS,
  DEFAULT_CHAT_TOOLS,
} from '@/data/chatCatalog'
import { PROJECTS } from '@/data/projects'
import type { PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'
import { ChatComposer } from './ChatComposer'
import { ChatEmptyState } from './ChatEmptyState'

interface ChatPanelProps {
  panelKey: PanelKey
}

export function ChatPanel({ panelKey }: ChatPanelProps) {
  const currentProjectId = usePlaygroundStore((s) => s.currentProjectId)
  const instanceState = usePlaygroundStore((s) => s.instanceState[panelKey])
  const ensureInstanceState = usePlaygroundStore((s) => s.ensureInstanceState)
  const setChatConv = usePlaygroundStore((s) => s.setChatConv)
  const appendChatMessage = usePlaygroundStore((s) => s.appendChatMessage)
  const openPanelType = usePlaygroundStore((s) => s.openPanelType)
  const [draft, setDraft] = useState('')

  const p = PROJECTS[currentProjectId]
  const st =
    instanceState ||
    ensureInstanceState(panelKey, {
      convId: p?.convs[0]?.id,
      title: p?.convs[0]?.title,
      messages: p ? JSON.parse(JSON.stringify(p.messages)) : [],
      model: DEFAULT_CHAT_MODEL,
      enabledTools: DEFAULT_CHAT_TOOLS,
      enabledMcps: DEFAULT_CHAT_MCPS,
      enabledSkills: DEFAULT_CHAT_SKILLS,
      chatMode: 'ask',
      railCollapsed: false,
    })

  const model = st.model || DEFAULT_CHAT_MODEL
  const tools = st.enabledTools || DEFAULT_CHAT_TOOLS
  const mcps = st.enabledMcps || DEFAULT_CHAT_MCPS
  const skills = st.enabledSkills || DEFAULT_CHAT_SKILLS
  const mode = st.chatMode || 'ask'
  const railCollapsed = !!st.railCollapsed
  const messages = st.messages || []
  const isEmpty = messages.length === 0

  const send = () => {
    const text = draft.trim()
    if (!text) return
    appendChatMessage(panelKey, text)
    setDraft('')
  }

  const newChat = () =>
    ensureInstanceState(panelKey, {
      convId: `n${Date.now()}`,
      title: 'New chat',
      messages: [],
    })

  return (
    <div
      className={`chat-layout${railCollapsed ? ' chat-layout--rail-collapsed' : ''}`}
      data-chat-instance={panelKey}
    >
      <aside className="conv-rail">
        <div className="conv-head">
          <div className="conv-head-row">
            <div>
              <h2>Chats</h2>
              <p className="conv-sub">{p?.name}</p>
            </div>
            <Button
              variant="plain"
              size="sm"
              className="conv-collapse-btn"
              title="Collapse conversation list"
              aria-label="Collapse conversation list"
              onClick={() => ensureInstanceState(panelKey, { railCollapsed: true })}
            >
              <AngleLeftIcon />
            </Button>
          </div>
          <div className="conv-actions">
            <Button
              variant="secondary"
              size="sm"
              className="conv-action-new"
              icon={<PlusIcon />}
              onClick={newChat}
            >
              New chat
            </Button>
            <Button
              variant="plain"
              size="sm"
              className="conv-action-panel"
              title="Open in new Chat panel"
              aria-label="Open in new Chat panel"
              icon={<ExternalLinkAltIcon />}
              onClick={() => openPanelType('chat')}
            />
          </div>
        </div>
        <div className="conv-list">
          {p?.convs.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`conv-item${c.id === st.convId ? ' active' : ''}`}
              onClick={() => setChatConv(panelKey, c.id)}
            >
              <span className="ct">{c.title}</span>
              <span className="cm">{c.meta}</span>
            </button>
          ))}
        </div>
      </aside>

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
        {!isEmpty ? (
          <div className="chat-header">
            <span className="title">{st.title || 'Chat'}</span>
            <span className="pill">
              <strong>{mode === 'auto' ? 'Auto' : 'Ask'}</strong>
            </span>
          </div>
        ) : null}

        <div className={`messages${isEmpty ? ' messages--empty' : ''}`}>
          {isEmpty ? (
            <ChatEmptyState
              onSuggestion={(text) => {
                setDraft(text)
              }}
            />
          ) : (
            messages.map((m, i) => {
              if (m.role === 'user') {
                return (
                  <div className="msg user" key={i}>
                    <div className="msg-avatar">U</div>
                    <div className="bubble">
                      <p>{m.text}</p>
                    </div>
                  </div>
                )
              }
              return (
                <div className="msg assistant" key={i}>
                  <div className="msg-avatar">AI</div>
                  <div className="bubble">
                    {m.thinking ? <div className="thinking">{m.thinking}</div> : null}
                    {m.tool ? (
                      <div className="tool-card">
                        <div className="tool-card-head">
                          <span>🛠 {m.tool.title}</span>
                          <span className="ok">✓ done</span>
                        </div>
                        <pre>{m.tool.body}</pre>
                      </div>
                    ) : null}
                    {m.text ? (
                      <p
                        dangerouslySetInnerHTML={{
                          __html: m.text.replace(
                            /\*\*(.+?)\*\*/g,
                            '<strong>$1</strong>',
                          ),
                        }}
                      />
                    ) : null}
                  </div>
                </div>
              )
            })
          )}
        </div>

        <ChatComposer
          draft={draft}
          onDraftChange={setDraft}
          onSend={send}
          model={model}
          tools={tools}
          mcps={mcps}
          skills={skills}
          mode={mode}
          onModelChange={(id) => ensureInstanceState(panelKey, { model: id })}
          onToolsChange={(ids) => ensureInstanceState(panelKey, { enabledTools: ids })}
          onMcpsChange={(ids) => ensureInstanceState(panelKey, { enabledMcps: ids })}
          onSkillsChange={(ids) =>
            ensureInstanceState(panelKey, { enabledSkills: ids })
          }
          onModeChange={(m) => ensureInstanceState(panelKey, { chatMode: m })}
        />
      </div>
    </div>
  )
}
