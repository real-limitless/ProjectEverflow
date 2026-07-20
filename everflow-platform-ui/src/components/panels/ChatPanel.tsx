import { useState } from 'react'
import { Button } from '@patternfly/react-core'
import { PROJECTS } from '@/data/projects'
import type { PanelKey } from '@/types/panels'
import { usePlaygroundStore } from '@/store/playgroundStore'

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
  const [mode, setMode] = useState<'ask' | 'auto'>('ask')

  const p = PROJECTS[currentProjectId]
  const st =
    instanceState ||
    ensureInstanceState(panelKey, {
      convId: p?.convs[0]?.id,
      title: p?.convs[0]?.title,
      messages: p ? JSON.parse(JSON.stringify(p.messages)) : [],
    })

  const send = () => {
    const text = draft.trim()
    if (!text) return
    appendChatMessage(panelKey, text)
    setDraft('')
  }

  return (
    <div className="chat-layout" data-chat-instance={panelKey}>
      <aside className="conv-rail">
        <div className="conv-head">
          <h2>Conversations · {p?.name}</h2>
          <Button
            variant="primary"
            onClick={() =>
              ensureInstanceState(panelKey, {
                convId: `n${Date.now()}`,
                title: 'New chat',
                messages: [],
              })
            }
          >
            + New chat
          </Button>
          <Button
            variant="secondary"
            size="sm"
            title="Open conversation in a new Chat panel"
            onClick={() => openPanelType('chat')}
          >
            ↗ New panel
          </Button>
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
      <div className="chat-main">
        <div className="chat-header">
          <span className="title">{st.title || 'Chat'}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="pill" title={panelKey}>
              <strong>panel</strong> {String(panelKey).split(':')[1] || ''}
            </span>
            <span className="pill">
              <strong>Agent</strong> Coding
            </span>
            <span className="pill">
              <strong>auto</strong>
            </span>
            <div className="mode-toggle">
              <button
                type="button"
                className={mode === 'ask' ? 'active' : ''}
                onClick={() => setMode('ask')}
              >
                Ask
              </button>
              <button
                type="button"
                className={mode === 'auto' ? 'active' : ''}
                onClick={() => setMode('auto')}
              >
                ⚡ Auto
              </button>
            </div>
          </div>
        </div>
        <div className="messages">
          {(st.messages || []).map((m, i) => {
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
                  {m.text ? <p>{m.text}</p> : null}
                </div>
              </div>
            )
          })}
        </div>
        <div className="composer-wrap">
          <div className="composer">
            <textarea
              rows={2}
              placeholder="Ask to fix bugs, commit, push… (/ skills)"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <div className="composer-bar">
              <div className="composer-tools">
                <button className="chip" type="button">
                  Tools
                </button>
                <button className="chip" type="button">
                  Sandbox
                </button>
                <button className="chip" type="button">
                  Git
                </button>
              </div>
              <Button variant="primary" className="send-btn" onClick={send} title="Send">
                ➤
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
