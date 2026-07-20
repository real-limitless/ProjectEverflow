import { useEffect, useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  MenuToggle,
  Popover,
  Select,
  SelectList,
  SelectOption,
} from '@patternfly/react-core'
import ClockIcon from '@patternfly/react-icons/dist/esm/icons/clock-icon'
import PaperPlaneIcon from '@patternfly/react-icons/dist/esm/icons/paper-plane-icon'
import BoltIcon from '@patternfly/react-icons/dist/esm/icons/bolt-icon'
import WrenchIcon from '@patternfly/react-icons/dist/esm/icons/wrench-icon'
import OutlinedStarIcon from '@patternfly/react-icons/dist/esm/icons/outlined-star-icon'
import {
  CHAT_MCPS,
  CHAT_MODELS,
  CHAT_SKILLS,
  CHAT_TOOLS,
} from '@/data/chatCatalog'

interface ChatComposerProps {
  draft: string
  onDraftChange: (v: string) => void
  onSend: () => void
  model: string
  tools: string[]
  mcps: string[]
  skills: string[]
  mode: 'ask' | 'auto'
  onModelChange: (id: string) => void
  onToolsChange: (ids: string[]) => void
  onMcpsChange: (ids: string[]) => void
  onSkillsChange: (ids: string[]) => void
  onModeChange: (mode: 'ask' | 'auto') => void
}

function toggle(list: string[], id: string) {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
}

export function ChatComposer({
  draft,
  onDraftChange,
  onSend,
  model,
  tools,
  mcps,
  skills,
  mode,
  onModelChange,
  onToolsChange,
  onMcpsChange,
  onSkillsChange,
  onModeChange,
}: ChatComposerProps) {
  const taRef = useRef<HTMLTextAreaElement>(null)
  const [modelOpen, setModelOpen] = useState(false)

  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [draft])

  const modelLabel = CHAT_MODELS.find((m) => m.id === model)?.label || model

  return (
    <div className="chat-composer">
      <div className="chat-composer-pill">
        <textarea
          ref={taRef}
          rows={1}
          className="chat-composer-input"
          placeholder="Message… (type / for skills)"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
          aria-label="Message"
        />
        <div className="chat-composer-actions">
          <Popover
            position="top"
            hasAutoWidth
            bodyContent={
              <div className="composer-popover-list">
                <div className="composer-popover-title">Tools</div>
                {CHAT_TOOLS.map((t) => (
                  <Checkbox
                    key={t.id}
                    id={`ct-${t.id}`}
                    label={t.label}
                    description={t.description}
                    isChecked={tools.includes(t.id)}
                    onChange={() => onToolsChange(toggle(tools, t.id))}
                  />
                ))}
                <div className="composer-popover-title">MCP servers</div>
                {CHAT_MCPS.map((m) => (
                  <Checkbox
                    key={m.id}
                    id={`cm-${m.id}`}
                    label={m.label}
                    description={m.description}
                    isChecked={mcps.includes(m.id)}
                    onChange={() => onMcpsChange(toggle(mcps, m.id))}
                  />
                ))}
              </div>
            }
          >
            <button
              type="button"
              className="composer-icon-btn"
              title="Tools & MCPs"
            >
              <WrenchIcon />
              <span className="composer-icon-count">{tools.length + mcps.length}</span>
            </button>
          </Popover>

          <Popover
            position="top"
            hasAutoWidth
            bodyContent={
              <div className="composer-popover-list">
                <div className="composer-popover-title">Skills</div>
                {CHAT_SKILLS.map((s) => (
                  <Checkbox
                    key={s.id}
                    id={`cs-${s.id}`}
                    label={s.label}
                    description={s.description}
                    isChecked={skills.includes(s.id)}
                    onChange={() => onSkillsChange(toggle(skills, s.id))}
                  />
                ))}
              </div>
            }
          >
            <button type="button" className="composer-icon-btn" title="Skills">
              <OutlinedStarIcon />
              <span className="composer-icon-count">{skills.length}</span>
            </button>
          </Popover>

          <button
            type="button"
            className={`composer-icon-btn${mode === 'auto' ? ' is-on' : ''}`}
            title={mode === 'auto' ? 'Auto mode on' : 'Ask mode — click for Auto'}
            onClick={() => onModeChange(mode === 'auto' ? 'ask' : 'auto')}
          >
            <BoltIcon />
          </button>

          <Select
            isOpen={modelOpen}
            selected={model}
            onSelect={(_e, v) => {
              onModelChange(String(v))
              setModelOpen(false)
            }}
            onOpenChange={setModelOpen}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                variant="plain"
                className="composer-model-toggle"
                onClick={() => setModelOpen(!modelOpen)}
                isExpanded={modelOpen}
                icon={<ClockIcon />}
                title={`Model: ${modelLabel}`}
              />
            )}
          >
            <SelectList>
              {CHAT_MODELS.map((m) => (
                <SelectOption key={m.id} value={m.id} description={m.description}>
                  {m.label}
                </SelectOption>
              ))}
            </SelectList>
          </Select>

          <Button
            variant="primary"
            className="chat-composer-send"
            aria-label="Send"
            title="Send"
            isDisabled={!draft.trim()}
            onClick={onSend}
            icon={<PaperPlaneIcon />}
          />
        </div>
      </div>
      <div className="chat-composer-hint">
        Enter to send · Shift+Enter newline · / for skills · {mode === 'auto' ? 'Auto' : 'Ask'} ·{' '}
        {modelLabel}
      </div>
    </div>
  )
}
