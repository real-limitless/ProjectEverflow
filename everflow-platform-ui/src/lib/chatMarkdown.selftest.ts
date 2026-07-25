/**
 * Run: npx tsx src/lib/chatMarkdown.selftest.ts
 */
import { markdownToHtml } from './chatMarkdown'

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg)
}

const multi = markdownToHtml('Intro\n\n```python\nprint("hi")\nprint("bye")\n```\n\nDone')
assert(multi.includes('<pre class="md-code">'), 'has pre')
assert(multi.includes('print(&quot;hi&quot;)'), 'escaped code')
assert(!multi.includes('&lt;/code&gt;'), 'no escaped closing code tag as text')
assert(!multi.includes('&lt;/pre&gt;'), 'no escaped closing pre as text')
assert(multi.includes('lang-python'), 'language class')
assert(multi.includes('<p>Done</p>') || multi.includes('Done'), 'after fence')

const incomplete = markdownToHtml('```js\nconst x = 1')
assert(incomplete.includes('<pre class="md-code">'), 'streaming fence → pre')
assert(incomplete.includes('const x = 1'), 'streaming body')

const inline = markdownToHtml('Use `foo` and **bold**')
assert(inline.includes('md-inline'), 'inline code')
assert(inline.includes('<strong>bold</strong>'), 'bold')

console.log('chatMarkdown.selftest: ok')
