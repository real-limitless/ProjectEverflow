import OutlinedCommentsIcon from '@patternfly/react-icons/dist/esm/icons/outlined-comments-icon'

const DEFAULT_SUGGESTIONS = [
  'What tools and skills can you use?',
  'Open a canvas and sketch a short plan',
  'Search the web and build a mind map of the findings',
]

interface ChatEmptyStateProps {
  onSuggestion: (text: string) => void
  title?: string
  description?: string
  suggestions?: string[]
}

export function ChatEmptyState({
  onSuggestion,
  title = 'Start chatting',
  description = 'Vibe code, workflows, and deploys — with sandbox tools, MCP servers, and skills. Pick a suggestion or type below.',
  suggestions = DEFAULT_SUGGESTIONS,
}: ChatEmptyStateProps) {
  return (
    <div className="chat-empty">
      <div className="chat-empty-icon" aria-hidden>
        <OutlinedCommentsIcon />
      </div>
      <h2 className="chat-empty-title">{title}</h2>
      <p className="chat-empty-desc">{description}</p>
      {suggestions.length > 0 ? (
        <div className="chat-empty-suggestions">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              className="chat-empty-chip"
              onClick={() => onSuggestion(s)}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
