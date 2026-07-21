import type { WebSearchHit } from '@/types/studio'

export const DEMO_SEARCH: WebSearchHit[] = [
  {
    id: 'ws1',
    title: 'Podman compose remote deploy',
    url: 'https://docs.example.com/podman-compose',
    snippet: 'Run compose files on a remote host with SSH and rootless Podman…',
    readerMarkdown: `# Podman compose remote deploy

Source: docs.example.com · Reader mode (ads and chrome removed)

## Overview

Podman Compose can target a remote host over SSH. This is useful when your laptop authors the stack and a server runs the containers rootless.

## Prerequisites

- Podman 4+ on the remote host
- SSH key access for the deploy user
- A compose file with services, networks, and volumes

## Quick start

1. Export \`CONTAINER_HOST\` to the remote Podman socket
2. Run \`podman compose -f compose.yml up -d\`
3. Verify with \`podman ps\`

## Tips

- Prefer rootless sockets when possible
- Pin image digests for production
- Keep secrets out of compose; inject via environment or a vault

## See also

Remote sockets, systemd user services, and healthchecks for long-running stacks.
`,
  },
  {
    id: 'ws2',
    title: 'pgvector embeddings for RAG',
    url: 'https://docs.example.com/pgvector',
    snippet: 'Chunk documents, embed with your model, store vectors for retrieval…',
    readerMarkdown: `# pgvector embeddings for RAG

Source: docs.example.com · Reader mode

## Why vectors

Retrieval-augmented generation stores document chunks as embeddings so the model can fetch relevant context at answer time.

## Pipeline

1. **Ingest** — Markdown, OCR output, or cleaned web text
2. **Chunk** — Split by headings or token windows with overlap
3. **Embed** — Call your embedding model
4. **Store** — Insert into a \`vector\` column (pgvector)
5. **Retrieve** — Similarity search at chat time

## Schema sketch

\`\`\`sql
CREATE TABLE knowledge_chunks (
  id uuid PRIMARY KEY,
  project_id text,
  content text,
  embedding vector(1536)
);
\`\`\`

## Good defaults

- 500–800 token chunks with 10–15% overlap
- Metadata: source URL, canvas id, updated_at
- Re-index when the canvas Markdown changes
`,
  },
  {
    id: 'ws3',
    title: 'n8n workflow import format',
    url: 'https://docs.n8n.io/workflows/export-import/',
    snippet: 'Export workflows as JSON and map nodes when importing…',
    readerMarkdown: `# n8n workflow export and import

Source: docs.n8n.io · Reader mode

## Export

From the editor, export a workflow as JSON. The file includes nodes, connections, and settings (credentials are usually stripped or referenced by id).

## Import

1. Open **Import from file** or paste JSON
2. Map missing credentials
3. Validate node parameters for your environment

## Everflow note

Workflow graphs in Studio can import a subset of n8n node types. Prefer trigger → LLM → HTTP → code chains for the demo importer.
`,
  },
]

export function ocrMarkdownForFile(fileName: string): string {
  const title = fileName.replace(/\.(pdf|PDF)$/, '')
  return `# ${title}

> Converted from **${fileName}** via **Unlimited OCR** (demo).

## Extracted pages

### Page 1

Body text from the uploaded PDF, normalized to Markdown for embedding and chat retrieval.

- Headings preserved where detected
- Lists and tables simplified
- Images replaced with captions when present

### Page 2

Additional sections continue here so chunking has enough material for the vector store.

## Next steps

1. Review the Markdown in **Source** or **Preview**
2. Edit anything OCR misread
3. Wait for **chunking → embedding → indexed** so the chatbot can use this knowledge
`
}

export function summarizeReader(title: string, markdown: string): string {
  const words = markdown.replace(/[#>*`-]/g, ' ').split(/\s+/).filter(Boolean)
  const preview = words.slice(0, 40).join(' ')
  return `**Summary of “${title}”** (demo): ${preview}${words.length > 40 ? '…' : ''}`
}

export function researchReply(userText: string, articleTitle: string): string {
  const q = userText.trim().toLowerCase()
  if (q.includes('summar') || q.includes('tldr')) {
    return `Here’s a short take on **${articleTitle}**: it covers practical steps and defaults you can apply in this project. Pin it to Knowledge if you want the main chatbot to retrieve it later.`
  }
  if (q.includes('how') || q.includes('step')) {
    return `From **${articleTitle}**, focus on the ordered steps in the article body. I can help turn them into a checklist canvas if you add this page to Knowledge.`
  }
  return `Based on **${articleTitle}** (reader mode only — ephemeral chat): ${userText.trim() ? 'I would cross-check the article sections against your stack and cite the cleaned Markdown, not the original page chrome.' : 'Ask me to summarize, extract steps, or compare with your project.'}`
}
