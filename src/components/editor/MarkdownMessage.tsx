import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface MarkdownMessageProps {
  content: string;
  reasoning?: string;
}

export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({ content, reasoning }) => {
  const [showReasoning, setShowReasoning] = React.useState(false);

  return (
    <div className="w-full space-y-2">
      {/* Reasoning section (if present) */}
      {reasoning && (
        <details
          open={showReasoning}
          onToggle={(e) => setShowReasoning((e.target as HTMLDetailsElement).open)}
          className="cursor-pointer group"
        >
          <summary className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors py-2 px-3 bg-muted/50 rounded group-open:bg-muted">
            {showReasoning ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
            <span>💭 Model Reasoning</span>
          </summary>
          <div className="mt-2 p-3 bg-muted/30 rounded text-sm text-muted-foreground whitespace-pre-wrap">
            {reasoning}
          </div>
        </details>
      )}

      {/* Main content with markdown rendering */}
      <div className="prose prose-sm dark:prose-invert max-w-none overflow-hidden">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Custom styling for code blocks
            code: ({ inline, className, children, ...props }: any) => (
              inline ? (
                <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                  {children}
                </code>
              ) : (
                <code className="block bg-muted p-3 rounded my-2 overflow-x-auto text-xs" {...props}>
                  {children}
                </code>
              )
            ),
            // Custom styling for links
            a: ({ href, children, ...props }: any) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
                {...props}
              >
                {children}
              </a>
            ),
            // Custom styling for headers
            h1: ({ children, ...props }: any) => (
              <h1 className="text-lg font-bold mt-4 mb-2" {...props}>{children}</h1>
            ),
            h2: ({ children, ...props }: any) => (
              <h2 className="text-base font-bold mt-3 mb-2" {...props}>{children}</h2>
            ),
            h3: ({ children, ...props }: any) => (
              <h3 className="text-sm font-semibold mt-2 mb-1" {...props}>{children}</h3>
            ),
            // Custom styling for lists
            ul: ({ children, ...props }: any) => (
              <ul className="list-disc list-inside space-y-1 my-2" {...props}>{children}</ul>
            ),
            ol: ({ children, ...props }: any) => (
              <ol className="list-decimal list-inside space-y-1 my-2" {...props}>{children}</ol>
            ),
            // Custom styling for tables
            table: ({ children, ...props }: any) => (
              <table className="border-collapse border border-border w-full text-sm my-2" {...props}>
                {children}
              </table>
            ),
            th: ({ children, ...props }: any) => (
              <th className="border border-border bg-muted/50 px-2 py-1 text-left font-semibold" {...props}>
                {children}
              </th>
            ),
            td: ({ children, ...props }: any) => (
              <td className="border border-border px-2 py-1" {...props}>{children}</td>
            ),
            // Custom styling for blockquotes
            blockquote: ({ children, ...props }: any) => (
              <blockquote
                className="border-l-4 border-primary pl-4 italic text-muted-foreground my-2"
                {...props}
              >
                {children}
              </blockquote>
            ),
            // Custom styling for paragraphs
            p: ({ children, ...props }: any) => (
              <p className="my-2 leading-relaxed" {...props}>{children}</p>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </div>
  );
};
