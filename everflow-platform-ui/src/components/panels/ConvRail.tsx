import { useState } from 'react'
import { Button } from '@patternfly/react-core'
import AngleLeftIcon from '@patternfly/react-icons/dist/esm/icons/angle-left-icon'
import ExternalLinkAltIcon from '@patternfly/react-icons/dist/esm/icons/external-link-alt-icon'
import PlusIcon from '@patternfly/react-icons/dist/esm/icons/plus-icon'
import MapPinIcon from '@patternfly/react-icons/dist/esm/icons/map-pin-icon'
import EllipsisVIcon from '@patternfly/react-icons/dist/esm/icons/ellipsis-v-icon'
import type { ChatConversation } from '@/types/panels'

interface ConvRailProps {
  projectName: string
  conversations: ChatConversation[]
  activeConvId?: string
  onSelect: (convId: string) => void
  onNewChat: () => void
  onOpenPanel: () => void
  onCollapse: () => void
  onPin: (convId: string) => void
  onRename: (convId: string, title: string) => void
  onDelete: (convId: string) => void
  onAiTitle: (convId: string) => void
}

export function ConvRail({
  projectName,
  conversations,
  activeConvId,
  onSelect,
  onNewChat,
  onOpenPanel,
  onCollapse,
  onPin,
  onRename,
  onDelete,
  onAiTitle,
}: ConvRailProps) {
  const [menuId, setMenuId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')

  const startRename = (c: ChatConversation) => {
    setRenamingId(c.id)
    setRenameDraft(c.title)
    setMenuId(null)
  }

  const commitRename = (id: string) => {
    onRename(id, renameDraft)
    setRenamingId(null)
  }

  return (
    <aside className="conv-rail">
      <div className="conv-head">
        <div className="conv-head-row">
          <div>
            <h2>Chats</h2>
            <p className="conv-sub">{projectName}</p>
          </div>
          <Button
            variant="plain"
            size="sm"
            className="conv-collapse-btn"
            title="Collapse conversation list"
            aria-label="Collapse conversation list"
            onClick={onCollapse}
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
            onClick={onNewChat}
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
            onClick={onOpenPanel}
          />
        </div>
      </div>
      <div className="conv-list">
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`conv-item-wrap${c.id === activeConvId ? ' active' : ''}${c.pinned ? ' pinned' : ''}`}
          >
            {renamingId === c.id ? (
              <form
                className="conv-rename-form"
                onSubmit={(e) => {
                  e.preventDefault()
                  commitRename(c.id)
                }}
              >
                <input
                  className="conv-rename-input"
                  value={renameDraft}
                  autoFocus
                  aria-label="Rename conversation"
                  onChange={(e) => setRenameDraft(e.target.value)}
                  onBlur={() => commitRename(c.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') setRenamingId(null)
                  }}
                />
              </form>
            ) : (
              <button
                type="button"
                className={`conv-item${c.id === activeConvId ? ' active' : ''}`}
                onClick={() => {
                  setMenuId(null)
                  onSelect(c.id)
                }}
              >
                <span className="ct">
                  {c.pinned ? (
                    <MapPinIcon className="conv-pin-icon" aria-hidden />
                  ) : null}
                  {c.title}
                </span>
                <span className="cm">{c.meta}</span>
              </button>
            )}
            <div className="conv-item-tools">
              <button
                type="button"
                className={`conv-tool-btn${c.pinned ? ' is-on' : ''}`}
                title={c.pinned ? 'Unpin' : 'Pin'}
                aria-label={c.pinned ? 'Unpin conversation' : 'Pin conversation'}
                onClick={(e) => {
                  e.stopPropagation()
                  onPin(c.id)
                }}
              >
                <MapPinIcon />
              </button>
              <button
                type="button"
                className="conv-tool-btn"
                title="Conversation actions"
                aria-label="Conversation actions"
                aria-expanded={menuId === c.id}
                onClick={(e) => {
                  e.stopPropagation()
                  setMenuId(menuId === c.id ? null : c.id)
                }}
              >
                <EllipsisVIcon />
              </button>
              {menuId === c.id ? (
                <div className="conv-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => startRename(c)}>
                    Rename
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onAiTitle(c.id)
                      setMenuId(null)
                    }}
                  >
                    AI subject title
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      onPin(c.id)
                      setMenuId(null)
                    }}
                  >
                    {c.pinned ? 'Unpin' : 'Pin'}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="danger"
                    onClick={() => {
                      if (window.confirm(`Delete “${c.title}”?`)) {
                        onDelete(c.id)
                      }
                      setMenuId(null)
                    }}
                  >
                    Delete
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}
