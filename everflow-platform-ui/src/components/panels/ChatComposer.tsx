import { useEffect, useMemo, useRef, useState } from 'react'
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
import StopIcon from '@patternfly/react-icons/dist/esm/icons/stop-icon'
import UsersIcon from '@patternfly/react-icons/dist/esm/icons/users-icon'
import WrenchIcon from '@patternfly/react-icons/dist/esm/icons/wrench-icon'
import OutlinedStarIcon from '@patternfly/react-icons/dist/esm/icons/outlined-star-icon'
import {
  CHAT_MCPS,
  CHAT_MODELS,
  CHAT_SKILLS,
  CHAT_TOOLS,
  OPENCODE_AGENT_FALLBACKS,
  modeLabel,
  type CatalogItem,
} from '@/data/chatCatalog'
import type { ChatMode } from '@/types/panels'

interface ChatComposerProps {
  draft: string
  onDraftChange: (v: string) => void
  onSend: () => void
  model: string
  tools: string[]
  mcps: string[]
  skills: string[]
  /** Primary OpenCode agent for this conversation */
  agent: string
  mode: ChatMode
  onModelChange: (id: string) => void
  onToolsChange: (ids: string[]) => void
  onMcpsChange: (ids: string[]) => void
  onSkillsChange: (ids: string[]) => void
  onAgentChange: (id: string) => void
  /** Live catalogs from OpenCode (optional) */
  modelOptions?: CatalogItem[]
  /** Full OpenCode catalog for browse (defaults to modelOptions) */
  allModelOptions?: CatalogItem[]
  /** Pinned model ids shown first in the quick menu */
  pinnedModelIds?: string[]
  onBrowseModels?: () => void
  mcpOptions?: CatalogItem[]
  agentOptions?: CatalogItem[]
  sendDisabled?: boolean
  /** True while a prompt / agent turn is in flight */
  isRunning?: boolean
  onStop?: () => void
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
  agent,
  mode,
  onModelChange,
  onToolsChange,
  onMcpsChange,
  onSkillsChange,
  onAgentChange,
  modelOptions,
  allModelOptions,
  pinnedModelIds,
  onBrowseModels,
  mcpOptions,
  agentOptions,
  sendDisabled,
  isRunning,
  onStop,
}: ChatComposerProps) {
  const taRef = useRef<HTMLTextAreaElement>(null)
  const [modelOpen, setModelOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)

  useEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [draft])

  const fullModels = allModelOptions?.length
    ? allModelOptions
    : modelOptions?.length
      ? modelOptions
      : CHAT_MODELS

  const modelList = useMemo(() => {
    const pin = pinnedModelIds || []
    const byId = new Map(fullModels.map((m) => [m.id, m]))
    const pinned = pin.map((id) => byId.get(id)).filter(Boolean) as CatalogItem[]
    // Quick menu: pinned + current selection + a few catalog fallbacks
    const rest = fullModels.filter((m) => !pin.includes(m.id) && m.id !== model).slice(0, 8)
    const current =
      model && !pinned.some((m) => m.id === model) && !rest.some((m) => m.id === model)
        ? byId.get(model) || { id: model, label: model, description: 'Selected' }
        : null
    const base = modelOptions?.length ? modelOptions : CHAT_MODELS
    if (!pin.length && !current) return base
    const merged: CatalogItem[] = []
    const seen = new Set<string>()
    for (const m of [...pinned, ...(current ? [current] : []), ...rest, ...base]) {
      if (seen.has(m.id)) continue
      seen.add(m.id)
      merged.push(m)
    }
    return merged
  }, [fullModels, model, modelOptions, pinnedModelIds])

  const mcpList = mcpOptions?.length ? mcpOptions : CHAT_MCPS
  const agentList = agentOptions?.length ? agentOptions : OPENCODE_AGENT_FALLBACKS
  const modelLabel = fullModels.find((m) => m.id === model)?.label || model
  const agentLabel = agentList.find((a) => a.id === agent)?.label || agent || 'agent'
  // Ensure current selection appears even if not in catalog yet
  const agentListWithCurrent =
    agent && !agentList.some((a) => a.id === agent)
      ? [{ id: agent, label: agent, description: 'Selected' }, ...agentList]
      : agentList

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
            if (e.key === 'Enter' && !e.shiftKey && !isRunning) {
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
                {mcpOptions?.length ? (
                  <p className="composer-popover-hint">
                    Unchecked servers are denied on the next prompt via tools permissions.
                    Checked servers inherit agent / harness allow rules.
                  </p>
                ) : null}
                {mcpList.map((m) => (
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

          <Select
            isOpen={agentOpen}
            selected={agent}
            onSelect={(_e, v) => {
              onAgentChange(String(v))
              setAgentOpen(false)
            }}
            onOpenChange={setAgentOpen}
            toggle={(toggleRef) => (
              <MenuToggle
                ref={toggleRef}
                variant="plain"
                className="composer-agent-toggle"
                onClick={() => setAgentOpen(!agentOpen)}
                isExpanded={agentOpen}
                icon={<UsersIcon />}
                title={`Agent: ${agentLabel}`}
              >
                <span className="composer-agent-label">{agentLabel}</span>
              </MenuToggle>
            )}
          >
            <SelectList>
              {agentListWithCurrent.map((a) => (
                <SelectOption key={a.id} value={a.id} description={a.description}>
                  {a.label}
                </SelectOption>
              ))}
            </SelectList>
          </Select>

          <Select
            isOpen={modelOpen}
            selected={model}
            onSelect={(_e, v) => {
              const id = String(v)
              if (id === '__browse__') {
                setModelOpen(false)
                onBrowseModels?.()
                return
              }
              onModelChange(id)
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
              {modelList.map((m) => (
                <SelectOption key={m.id} value={m.id} description={m.description}>
                  {(pinnedModelIds || []).includes(m.id) ? '★ ' : ''}
                  {m.label}
                </SelectOption>
              ))}
              {onBrowseModels ? (
                <SelectOption value="__browse__" description="Search and pin OpenCode models">
                  Browse all models…
                </SelectOption>
              ) : null}
            </SelectList>
          </Select>

          {isRunning ? (
            <Button
              variant="primary"
              className="chat-composer-send chat-composer-stop"
              aria-label="Stop generating"
              title="Stop generating"
              onClick={onStop}
              icon={<StopIcon />}
            />
          ) : (
            <Button
              variant="primary"
              className="chat-composer-send"
              aria-label="Send"
              title="Send"
              isDisabled={!draft.trim() || !!sendDisabled}
              onClick={onSend}
              icon={<PaperPlaneIcon />}
            />
          )}
        </div>
      </div>
      <div className="chat-composer-hint">
        Enter to send · Shift+Enter newline · / for skills · {modeLabel(mode)} ·{' '}
        {agentLabel} · {modelLabel}
      </div>
    </div>
  )
}
