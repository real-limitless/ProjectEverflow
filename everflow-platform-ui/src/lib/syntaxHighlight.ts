export type LintSeverity = 'error' | 'warning' | 'info'

export interface LintDiagnostic {
  line: number // 1-based
  severity: LintSeverity
  message: string
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/** True when content is already pre-tokenized HTML (demo seeds). */
export function isPreHighlighted(src: string): boolean {
  return /class=["']tok-/.test(src)
}

/**
 * Lightweight syntax highlighter for demo code.
 * Supports JS/TS/TSX/JSX-ish, CSS, HTML, Markdown, JSON, shell.
 */
export function highlightCode(source: string, fileName = ''): string {
  if (!source) return ''
  if (isPreHighlighted(source)) return source

  const ext = fileName.includes('.')
    ? fileName.slice(fileName.lastIndexOf('.') + 1).toLowerCase()
    : ''

  if (ext === 'md' || ext === 'mdx') return highlightMarkdown(source)
  if (ext === 'css' || ext === 'scss') return highlightCss(source)
  if (ext === 'html' || ext === 'htm' || ext === 'svg') return highlightHtml(source)
  if (ext === 'json') return highlightJson(source)
  if (ext === 'sh' || ext === 'bash' || ext === 'zsh') return highlightShell(source)
  // default: JS/TS family and plain text with shared tokenizer
  return highlightJsFamily(source)
}

function highlightMarkdown(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      if (/^#{1,6}\s/.test(line)) {
        return `<span class="tok-kw">${escapeHtml(line)}</span>`
      }
      if (/^>\s?/.test(line)) {
        return `<span class="tok-com">${escapeHtml(line)}</span>`
      }
      if (/^[-*]\s/.test(line) || /^\d+\.\s/.test(line)) {
        return escapeHtml(line).replace(
          /^([-*\d.]+)/,
          '<span class="tok-fn">$1</span>',
        )
      }
      if (/^```/.test(line)) {
        return `<span class="tok-attr">${escapeHtml(line)}</span>`
      }
      // inline code / bold-ish
      let out = escapeHtml(line)
      out = out.replace(/`([^`]+)`/g, '<span class="tok-str">`$1`</span>')
      out = out.replace(/\*\*([^*]+)\*\*/g, '<span class="tok-fn">**$1**</span>')
      return out
    })
    .join('\n')
}

function highlightCss(src: string): string {
  let i = 0
  let out = ''
  while (i < src.length) {
    // comments
    if (src[i] === '/' && src[i + 1] === '*') {
      const end = src.indexOf('*/', i + 2)
      const chunk = end < 0 ? src.slice(i) : src.slice(i, end + 2)
      out += `<span class="tok-com">${escapeHtml(chunk)}</span>`
      i += chunk.length
      continue
    }
    // strings
    if (src[i] === '"' || src[i] === "'") {
      const q = src[i]
      let j = i + 1
      while (j < src.length && src[j] !== q) {
        if (src[j] === '\\') j++
        j++
      }
      const chunk = src.slice(i, Math.min(j + 1, src.length))
      out += `<span class="tok-str">${escapeHtml(chunk)}</span>`
      i += chunk.length
      continue
    }
    // selectors / properties — rough: identifiers before { or :
    const id = /^[a-zA-Z_@#.\-][\w\-@.#%]*/.exec(src.slice(i))
    if (id) {
      const word = id[0]
      const rest = src.slice(i + word.length).trimStart()
      if (rest.startsWith('{') || word.startsWith('@') || word.startsWith('.') || word.startsWith('#') || word.startsWith(':')) {
        out += `<span class="tok-tag">${escapeHtml(word)}</span>`
      } else if (rest.startsWith(':')) {
        out += `<span class="tok-attr">${escapeHtml(word)}</span>`
      } else {
        out += escapeHtml(word)
      }
      i += word.length
      continue
    }
    out += escapeHtml(src[i])
    i++
  }
  return out
}

function highlightHtml(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      let s = escapeHtml(line)
      s = s.replace(/(&lt;!--.*?--&gt;)/g, '<span class="tok-com">$1</span>')
      s = s.replace(
        /(&lt;\/?)([a-zA-Z][\w:-]*)/g,
        '$1<span class="tok-tag">$2</span>',
      )
      s = s.replace(
        /\b([a-zA-Z_:][\w:.-]*)(=)/g,
        '<span class="tok-attr">$1</span>$2',
      )
      s = s.replace(
        /(&quot;.*?&quot;|&#39;.*?&#39;)/g,
        '<span class="tok-str">$1</span>',
      )
      return s
    })
    .join('\n')
}

function highlightJson(src: string): string {
  let i = 0
  let out = ''
  while (i < src.length) {
    if (src[i] === '"') {
      let j = i + 1
      while (j < src.length && src[j] !== '"') {
        if (src[j] === '\\') j++
        j++
      }
      const str = src.slice(i, Math.min(j + 1, src.length))
      const after = src.slice(j + 1).trimStart()
      const cls = after.startsWith(':') ? 'tok-attr' : 'tok-str'
      out += `<span class="${cls}">${escapeHtml(str)}</span>`
      i = j + 1
      continue
    }
    if (/[-0-9]/.test(src[i])) {
      const m = /^-?\d+(\.\d+)?([eE][+-]?\d+)?/.exec(src.slice(i))
      if (m) {
        out += `<span class="tok-fn">${escapeHtml(m[0])}</span>`
        i += m[0].length
        continue
      }
    }
    if (/^(true|false|null)/.test(src.slice(i))) {
      const m = /^(true|false|null)/.exec(src.slice(i))!
      out += `<span class="tok-kw">${m[0]}</span>`
      i += m[0].length
      continue
    }
    out += escapeHtml(src[i])
    i++
  }
  return out
}

function highlightShell(src: string): string {
  return src
    .split('\n')
    .map((line) => {
      if (/^\s*#/.test(line)) {
        return `<span class="tok-com">${escapeHtml(line)}</span>`
      }
      let s = escapeHtml(line)
      s = s.replace(
        /^(\s*)(sudo|export|cd|npm|yarn|pnpm|git|echo|curl|ls|cat|node|python|docker)\b/,
        '$1<span class="tok-fn">$2</span>',
      )
      s = s.replace(/(["'])(?:\\.|(?!\1).)*\1/g, (m) => `<span class="tok-str">${m}</span>`)
      return s
    })
    .join('\n')
}

const JS_KEYWORDS = new Set([
  'break',
  'case',
  'catch',
  'class',
  'const',
  'continue',
  'debugger',
  'default',
  'delete',
  'do',
  'else',
  'enum',
  'export',
  'extends',
  'false',
  'finally',
  'for',
  'from',
  'function',
  'if',
  'implements',
  'import',
  'in',
  'instanceof',
  'interface',
  'let',
  'new',
  'null',
  'of',
  'return',
  'static',
  'super',
  'switch',
  'this',
  'throw',
  'true',
  'try',
  'type',
  'typeof',
  'undefined',
  'var',
  'void',
  'while',
  'with',
  'yield',
  'async',
  'await',
  'as',
  'readonly',
  'public',
  'private',
  'protected',
  'abstract',
  'declare',
  'namespace',
  'module',
  'satisfies',
  'keyof',
  'infer',
  'never',
  'unknown',
  'any',
  'boolean',
  'number',
  'string',
  'symbol',
  'bigint',
])

function highlightJsFamily(src: string): string {
  let i = 0
  let out = ''
  while (i < src.length) {
    // line comment
    if (src[i] === '/' && src[i + 1] === '/') {
      let j = i + 2
      while (j < src.length && src[j] !== '\n') j++
      out += `<span class="tok-com">${escapeHtml(src.slice(i, j))}</span>`
      i = j
      continue
    }
    // block comment
    if (src[i] === '/' && src[i + 1] === '*') {
      const end = src.indexOf('*/', i + 2)
      const chunk = end < 0 ? src.slice(i) : src.slice(i, end + 2)
      out += `<span class="tok-com">${escapeHtml(chunk)}</span>`
      i += chunk.length
      continue
    }
    // template / string
    if (src[i] === '"' || src[i] === "'" || src[i] === '`') {
      const q = src[i]
      let j = i + 1
      while (j < src.length) {
        if (src[j] === '\\') {
          j += 2
          continue
        }
        if (src[j] === q) {
          j++
          break
        }
        j++
      }
      out += `<span class="tok-str">${escapeHtml(src.slice(i, j))}</span>`
      i = j
      continue
    }
    // number
    if (/[0-9]/.test(src[i]) || (src[i] === '.' && /[0-9]/.test(src[i + 1] || ''))) {
      const m = /^(0x[\da-fA-F]+|0b[01]+|0o[0-7]+|\d+(\.\d+)?([eE][+-]?\d+)?)/.exec(
        src.slice(i),
      )
      if (m) {
        out += `<span class="tok-fn">${escapeHtml(m[0])}</span>`
        i += m[0].length
        continue
      }
    }
    // identifier / keyword
    if (/[A-Za-z_$]/.test(src[i])) {
      let j = i + 1
      while (j < src.length && /[\w$]/.test(src[j])) j++
      const word = src.slice(i, j)
      // skip whitespace to see if call
      let k = j
      while (k < src.length && /\s/.test(src[k])) k++
      if (JS_KEYWORDS.has(word)) {
        out += `<span class="tok-kw">${escapeHtml(word)}</span>`
      } else if (src[k] === '(') {
        out += `<span class="tok-fn">${escapeHtml(word)}</span>`
      } else if (/^[A-Z]/.test(word)) {
        out += `<span class="tok-tag">${escapeHtml(word)}</span>`
      } else {
        out += escapeHtml(word)
      }
      i = j
      continue
    }
    // JSX/HTML-ish tags in TSX
    if (src[i] === '<' && /[A-Za-z/!]/.test(src[i + 1] || '')) {
      // treat <Tag as tag token start only for simple cases
      const m = /^<\/?[A-Za-z][\w.-]*/.exec(src.slice(i))
      if (m) {
        out += `<span class="tok-tag">${escapeHtml(m[0])}</span>`
        i += m[0].length
        continue
      }
    }
    out += escapeHtml(src[i])
    i++
  }
  return out
}

/**
 * Demo-grade diagnostics (syntax lint hints) for the editor gutter.
 * Not a full language server — lightweight static checks.
 */
export function lintCode(source: string, fileName = ''): LintDiagnostic[] {
  // Work on plain text; strip pre-highlighted spans if present
  const plain = isPreHighlighted(source)
    ? source
        .replace(/<[^>]+>/g, '')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
    : source

  const lines = plain.split('\n')
  const diags: LintDiagnostic[] = []
  const ext = fileName.includes('.')
    ? fileName.slice(fileName.lastIndexOf('.') + 1).toLowerCase()
    : ''
  const isCode =
    /^(ts|tsx|js|jsx|mjs|cjs|css|scss|json|html|htm)$/.test(ext) || !ext

  lines.forEach((line, idx) => {
    const n = idx + 1
    if (/\s+$/.test(line) && line.length > 0) {
      diags.push({
        line: n,
        severity: 'info',
        message: 'Trailing whitespace',
      })
    }
    if (isCode && /\bconsole\.(log|debug|info)\s*\(/.test(line)) {
      diags.push({
        line: n,
        severity: 'warning',
        message: 'Unexpected console statement',
      })
    }
    if (/\bTODO\b|\bFIXME\b/.test(line)) {
      diags.push({
        line: n,
        severity: 'info',
        message: 'TODO/FIXME comment',
      })
    }
    if (isCode && /catch\s*\(\s*\w*\s*\)\s*\{\s*\}/.test(line)) {
      diags.push({
        line: n,
        severity: 'warning',
        message: 'Empty catch block',
      })
    }
    if (isCode && /\bvar\s+\w+/.test(line)) {
      diags.push({
        line: n,
        severity: 'warning',
        message: "Prefer 'const' or 'let' over 'var'",
      })
    }
    // Unmatched simple quote heuristic on non-comment lines
    if (isCode && !/^\s*(\/\/|\/\*|\*)/.test(line)) {
      const singles = (line.match(/'/g) || []).length
      const doubles = (line.match(/"/g) || []).length
      if (singles % 2 === 1 && !line.includes("\\'")) {
        // ignore apostrophes in words roughly
        if (!/\w'\w/.test(line) || singles > 1) {
          /* skip noisy apostrophe false positives */
        }
      }
      if (doubles % 2 === 1 && !line.includes('\\"')) {
        diags.push({
          line: n,
          severity: 'error',
          message: 'Possible unclosed string literal',
        })
      }
    }
    if (ext === 'json') {
      // bare none
    }
  })

  // Bracket balance for the whole file (report on last line)
  if (isCode && plain.trim()) {
    const pairs: Record<string, string> = { '(': ')', '[': ']', '{': '}' }
    const stack: string[] = []
    let inStr: string | null = null
    for (let i = 0; i < plain.length; i++) {
      const ch = plain[i]
      if (inStr) {
        if (ch === '\\') {
          i++
          continue
        }
        if (ch === inStr) inStr = null
        continue
      }
      if (ch === '"' || ch === "'" || ch === '`') {
        inStr = ch
        continue
      }
      if (ch === '/' && plain[i + 1] === '/') {
        while (i < plain.length && plain[i] !== '\n') i++
        continue
      }
      if (pairs[ch]) stack.push(pairs[ch])
      else if (ch === ')' || ch === ']' || ch === '}') {
        const want = stack.pop()
        if (want !== ch) {
          const line = plain.slice(0, i).split('\n').length
          diags.push({
            line,
            severity: 'error',
            message: `Unmatched '${ch}'`,
          })
        }
      }
    }
    if (stack.length) {
      diags.push({
        line: lines.length,
        severity: 'error',
        message: `Unclosed '${stack[stack.length - 1] === ')' ? '(' : stack[stack.length - 1] === ']' ? '[' : '{'}'`,
      })
    }
  }

  // one diagnostic per line (highest severity)
  const rank: Record<LintSeverity, number> = { error: 3, warning: 2, info: 1 }
  const byLine = new Map<number, LintDiagnostic>()
  for (const d of diags) {
    const prev = byLine.get(d.line)
    if (!prev || rank[d.severity] > rank[prev.severity]) byLine.set(d.line, d)
  }
  return [...byLine.values()].sort((a, b) => a.line - b.line)
}

/** Decode HTML entities in pre-highlighted demo code for plain-text tools. */
export function toPlainSource(source: string): string {
  if (!isPreHighlighted(source)) return source
  return source
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}
