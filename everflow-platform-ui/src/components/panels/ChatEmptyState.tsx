import OutlinedCommentsIcon from '@patternfly/react-icons/dist/esm/icons/outlined-comments-icon'

const SUGGESTIONS = [
  'What tools and skills can you use?',
  'Open a canvas and sketch a short plan',
  'Search the web and build a mind map of the findings',
]

interface ChatEmptyStateProps {
  onSuggestion: (text: string) => void
}

export function ChatEmptyState({ onSuggestion }: ChatEmptyStateProps) {
  return (
    <div className="chat-empty">
      <div className="chat-empty-icon" aria-hidden>
        <OutlinedCommentsIcon />
      </div>
      <h2 className="chat-empty-title">Start chatting</h2>
      <p className="chat-empty-desc">
        Vibe code, workflows, and deploys — with sandbox tools, MCP servers, and
        skills. Pick a suggestion or type below.
      </p>
      <div className="chat-empty-suggestions">
        {SUGGESTIONS.map((s) => (
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
    </div>
  )
}
