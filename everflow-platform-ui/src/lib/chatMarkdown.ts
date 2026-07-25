import type { ChatBlock, ChatMessage } from '@/types/panels'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderFenceHtml(lang: string, code: string): string {
  const cls = lang ? ` class="lang-${escapeHtml(lang)}"` : ''
  return `<pre class="md-code"><code${cls}>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`
}

/**
 * Lightweight Markdown → HTML for chat bubbles.
 *
 * Fenced code blocks are replaced with single-line placeholders before the
 * line-based paragraph pass, so multi-line ``` blocks are not split into
 * escaped </code></pre> text nodes.
 */
export function markdownToHtml(md: string): string {
  let src = md.replace(/\r\n/g, '\n')
  const blocks: string[] = []

  const stash = (html: string): string => {
    const i = blocks.length
    blocks.push(html)
    // Single-line sentinel (no newlines) so the line loop never splits HTML
    return `\uE000MD${i}\uE001`
  }

  // Closed fenced code blocks (language optional; newline after fence optional)
  src = src.replace(/```([^\n`]*)\n?([\s\S]*?)```/g, (_m, langRaw: string, code: string) => {
    const lang = (langRaw || '').trim().split(/\s+/)[0] || ''
    return stash(renderFenceHtml(lang, code))
  })

  // Incomplete streaming fence: open ``` without close → provisional code block
  src = src.replace(/```([^\n`]*)\n?([\s\S]*)$/g, (_m, langRaw: string, code: string) => {
    // Only if this looks like an unfinished fence (no closing ```)
    if (code.includes('```')) return _m
    const lang = (langRaw || '').trim().split(/\s+/)[0] || ''
    return stash(renderFenceHtml(lang, code || ''))
  })

  // Tables (simple pipe rows) — also stash so multi-line tables survive split
  src = src.replace(/(?:^\|.+\|[ \t]*\n)+/gm, (block) => {
    const rows = block.trim().split('\n').filter(Boolean)
    if (rows.length < 2) return block
    const parseRow = (row: string) =>
      row
        .replace(/^\||\|$/g, '')
        .split('|')
        .map((c) => c.trim())
    const isSep = (row: string) => /^\|?\s*:?-{3,}/.test(row)
    const header = parseRow(rows[0])
    const bodyRows = rows.slice(1).filter((r) => !isSep(r)).map(parseRow)
    if (!bodyRows.length && rows.length === 2 && isSep(rows[1])) {
      // header + separator only
    }
    const th = header.map((h) => `<th>${inlineMd(h)}</th>`).join('')
    const tr = bodyRows
      .map((cells) => `<tr>${cells.map((c) => `<td>${inlineMd(c)}</td>`).join('')}</tr>`)
      .join('')
    return stash(
      `<table class="md-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`,
    )
  })

  const lines = src.split('\n')
  const out: string[] = []
  let listBuf: string[] = []
  let listType: 'ul' | 'ol' | null = null

  const flushList = () => {
    if (!listType || !listBuf.length) return
    out.push(`<${listType}>${listBuf.join('')}</${listType}>`)
    listBuf = []
    listType = null
  }

  const isSentinel = (line: string) => /^\uE000MD\d+\uE001$/.test(line.trim())

  for (const line of lines) {
    if (isSentinel(line.trim()) || line.startsWith('<pre') || line.startsWith('<table')) {
      flushList()
      out.push(line.trim())
      continue
    }
    const h = /^(#{1,3})\s+(.+)$/.exec(line)
    if (h) {
      flushList()
      const level = h[1].length
      out.push(`<h${level} class="md-h">${inlineMd(h[2])}</h${level}>`)
      continue
    }
    const ul = /^[-*]\s+(.+)$/.exec(line)
    if (ul) {
      if (listType !== 'ul') {
        flushList()
        listType = 'ul'
      }
      listBuf.push(`<li>${inlineMd(ul[1])}</li>`)
      continue
    }
    const ol = /^(\d+)\.\s+(.+)$/.exec(line)
    if (ol) {
      if (listType !== 'ol') {
        flushList()
        listType = 'ol'
      }
      listBuf.push(`<li>${inlineMd(ol[2])}</li>`)
      continue
    }
    if (!line.trim()) {
      flushList()
      continue
    }
    flushList()
    out.push(`<p>${inlineMd(line)}</p>`)
  }
  flushList()

  let html = out.join('\n')
  html = html.replace(/\uE000MD(\d+)\uE001/g, (_m, idx: string) => {
    const i = Number(idx)
    return blocks[i] ?? ''
  })
  return html
}

function inlineMd(s: string): string {
  let t = escapeHtml(s)
  t = t.replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  t = t.replace(
    /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
  )
  return t
}

export function messageToMarkdown(msg: ChatMessage): string {
  const parts: string[] = []
  if (msg.thinking) parts.push(`_${msg.thinking}_`)
  if (msg.blocks?.length) {
    for (const b of msg.blocks) parts.push(blockToMarkdown(b))
  } else if (msg.text) {
    parts.push(msg.text)
  }
  if (msg.tool) {
    parts.push(`\`\`\`\n// ${msg.tool.title}\n${msg.tool.body}\n\`\`\``)
  }
  return parts.filter(Boolean).join('\n\n')
}

export function messageToRaw(msg: ChatMessage): string {
  const parts: string[] = []
  if (msg.thinking) parts.push(msg.thinking)
  if (msg.blocks?.length) {
    for (const b of msg.blocks) parts.push(blockToRaw(b))
  } else if (msg.text) {
    parts.push(msg.text)
  }
  if (msg.tool) {
    parts.push(`${msg.tool.title}\n${msg.tool.body}`)
  }
  return parts.filter(Boolean).join('\n\n')
}

function blockToMarkdown(b: ChatBlock): string {
  switch (b.type) {
    case 'markdown':
    case 'text':
      return b.text || ''
    case 'question':
      return `**Question:** ${b.text || ''}\n${(b.options || []).map((o) => `- ${o}`).join('\n')}`
    case 'image':
      return `![${b.alt || 'image'}](${b.imageUrl || ''})`
    case 'attachment':
      return `📎 ${b.attachment?.name || 'file'} (${b.attachment?.sizeLabel || ''})`
    case 'terminal':
      return `\`\`\`bash\n$ ${b.terminal?.command || ''}\n${b.terminal?.output || ''}\n\`\`\``
    case 'web_search': {
      const head = `**Web search:** ${b.webSearch?.query || ''}`
      const rows = (b.webSearch?.results || [])
        .map((r) => `- [${r.title}](${r.url}) — ${r.snippet}`)
        .join('\n')
      return `${head}\n${rows}`
    }
    case 'knowledge_citations': {
      const head = `**Knowledge sources:** ${b.knowledgeCitations?.query || ''}`
      const rows = (b.knowledgeCitations?.hits || [])
        .map(
          (h) =>
            `- ${h.canvasName}${h.score != null ? ` (${h.score})` : ''}: ${h.text.slice(0, 200)}`,
        )
        .join('\n')
      return `${head}\n${rows}`
    }
    case 'tool':
      return `\`\`\`\n// ${b.tool?.title || 'tool'}\n${b.tool?.body || ''}\n\`\`\``
    default:
      return b.text || ''
  }
}

function blockToRaw(b: ChatBlock): string {
  switch (b.type) {
    case 'markdown':
    case 'text':
    case 'question':
      return [b.text, ...(b.options || [])].filter(Boolean).join('\n')
    case 'image':
      return b.imageUrl || b.alt || ''
    case 'attachment':
      return `${b.attachment?.name || ''} ${b.attachment?.sizeLabel || ''}`.trim()
    case 'terminal':
      return `$ ${b.terminal?.command || ''}\n${b.terminal?.output || ''}`
    case 'web_search':
      return [
        b.webSearch?.query || '',
        ...(b.webSearch?.results || []).map((r) => `${r.title}\n${r.url}\n${r.snippet}`),
      ].join('\n')
    case 'knowledge_citations':
      return [
        b.knowledgeCitations?.query || '',
        ...(b.knowledgeCitations?.hits || []).map(
          (h) => `${h.canvasName}\n${h.text}`,
        ),
      ].join('\n')
    case 'tool':
      return `${b.tool?.title || ''}\n${b.tool?.body || ''}`
    default:
      return b.text || ''
  }
}

export function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 4))
}

export function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`
  return String(n)
}

export function newMessageId(prefix = 'm'): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

export function deriveTitleFromMessages(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user')
  const raw =
    firstUser?.text ||
    firstUser?.blocks?.find((b) => b.text)?.text ||
    'New chat'
  const cleaned = raw.replace(/\s+/g, ' ').trim()
  return cleaned.length > 48 ? `${cleaned.slice(0, 45)}…` : cleaned || 'New chat'
}
