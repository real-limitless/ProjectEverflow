import { markdownToHtml } from '@/lib/chatMarkdown'

export type MarkdownViewMode = 'edit' | 'preview'

interface MarkdownWorkbenchProps {
  value: string
  mode: MarkdownViewMode
  onChange: (next: string) => void
  readOnly?: boolean
  placeholder?: string
  ariaLabel?: string
}

/** Full-height Markdown edit or rich preview. Mode is controlled by the parent chrome. */
export function MarkdownWorkbench({
  value,
  mode,
  onChange,
  readOnly = false,
  placeholder = 'Write Markdown…',
  ariaLabel = 'Knowledge markdown',
}: MarkdownWorkbenchProps) {
  if (mode === 'edit') {
    return (
      <textarea
        className="canvas-md-source"
        value={value}
        readOnly={readOnly}
        placeholder={placeholder}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
    )
  }

  const html = value.trim()
    ? markdownToHtml(value)
    : '<p class="canvas-md-empty">Nothing to preview yet. Switch to Edit and write some Markdown.</p>'

  return (
    <div className="canvas-md-preview-scroll">
      <div
        className="canvas-md-preview msg-md"
        // Safe: markdownToHtml escapes user content
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  )
}
