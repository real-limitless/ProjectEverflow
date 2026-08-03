#!/usr/bin/env node
/**
 * Capture Everflow screenshots from a **live full stack** (Compose frontend :3000).
 *
 * Does NOT start Vite demo mode or `npm run dev`. The product UI must come from
 * the running containers (or any live BASE_URL).
 *
 * Typical flow:
 *   1. ./scripts/everflow install   # or start
 *   2. ./scripts/everflow setup-admin
 *   3. node scripts/capture-screenshots.mjs --live --start-stack   # optional auto-start
 *   4. Interactive playground: --interactive (you drive features; snap with captions)
 *
 * Auth (required for live):
 *   EVERFLOW_EMAIL / EVERFLOW_PASSWORD
 *   or EVERFLOW_ADMIN_EMAIL / EVERFLOW_ADMIN_PASSWORD
 *
 * Env: BASE_URL (default http://127.0.0.1:3000), API_URL, OUT_DIR, …
 * See scripts/screenshots/README.md
 */
import { spawn } from 'node:child_process'
import { createRequire } from 'node:module'
import { createInterface } from 'node:readline'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const REPO_ROOT = path.resolve(__dirname, '..')
const SCREENSHOTS_PKG = path.join(__dirname, 'screenshots')

/** App-level surfaces (authenticated live UI). */
const APP_SHOTS = [
  { file: '01-playground-home.png', path: '/', name: 'Playground home', caption: 'Playground (Studio) — project workbench entry' },
  { file: '02-marketplace.png', path: '/marketplace', name: 'Marketplace', caption: 'Marketplace — skills, tools, and MCP servers for sandboxes' },
  { file: '03-usage.png', path: '/usage', name: 'Usage', caption: 'Usage — AI token and activity metrics for the org' },
  { file: '04-overview.png', path: '/overview', name: 'Overview', caption: 'Overview — org dashboard surface' },
  { file: '05-plans.png', path: '/plans', name: 'Plans', caption: 'Plans & billing surface' },
  { file: '06-harnesses.png', path: '/harnesses', name: 'Harnesses', caption: 'Harnesses — agent runtimes available to projects' },
]

function parseArgs(argv) {
  const out = {
    baseUrl: process.env.BASE_URL || 'http://127.0.0.1:3000',
    apiUrl: process.env.API_URL || process.env.PUBLIC_API_URL || 'http://127.0.0.1:8000',
    outDir: process.env.OUT_DIR || path.join(REPO_ROOT, 'docs', 'screenshots'),
    width: Number(process.env.VIEWPORT_WIDTH || 1600),
    height: Number(process.env.VIEWPORT_HEIGHT || 1000),
    settleMs: Number(process.env.SETTLE_MS || 1500),
    email:
      process.env.EVERFLOW_EMAIL ||
      process.env.EVERFLOW_ADMIN_EMAIL ||
      '',
    password:
      process.env.EVERFLOW_PASSWORD ||
      process.env.EVERFLOW_ADMIN_PASSWORD ||
      '',
    startStack: false,
    interactive: false,
    appOnly: false,
    headed: false,
    fullPage: true,
    skipLogin: false,
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--base-url' && argv[i + 1]) out.baseUrl = argv[++i]
    else if (a === '--api-url' && argv[i + 1]) out.apiUrl = argv[++i]
    else if (a === '--out' && argv[i + 1]) out.outDir = path.resolve(argv[++i])
    else if (a === '--email' && argv[i + 1]) out.email = argv[++i]
    else if (a === '--password' && argv[i + 1]) out.password = argv[++i]
    else if (a === '--start-stack') out.startStack = true
    else if (a === '--live') {
      /* default is live; kept for clarity in docs */
    } else if (a === '--interactive' || a === '-i') {
      out.interactive = true
      out.headed = true
      if (!process.env.VIEWPORT_WIDTH) out.width = 1920
      if (!process.env.VIEWPORT_HEIGHT) out.height = 1080
    } else if (a === '--app-only') out.appOnly = true
    else if (a === '--headed') out.headed = true
    else if (a === '--viewport-only') out.fullPage = false
    else if (a === '--skip-login') out.skipLogin = true
    else if (a === '--help' || a === '-h') {
      console.log(`Usage: node scripts/capture-screenshots.mjs [options]

Live full-stack screenshots (Compose UI — no Vite demo / npm dev).

  --start-stack       Run ./scripts/everflow start (then wait for UI)
  --base-url URL      UI (default http://127.0.0.1:3000)
  --api-url URL       API for login (default http://127.0.0.1:8000)
  --email / --password
  --app-only          Capture app routes only, then exit
  --interactive, -i   Headed browser; you drive Playground, then snap
  --headed            Show browser during batch shots
  --out DIR           Output root (default docs/screenshots)

Interactive commands (stdin or docs/screenshots/.capture-cmd):
  snap [file] [caption words…]
  caption <text>          set caption for last snap
  goto /path
  reload | quit

Captions are written to docs/screenshots/CAPTIONS.md

Env: BASE_URL, API_URL, EVERFLOW_EMAIL, EVERFLOW_PASSWORD, OUT_DIR, …
`)
      process.exit(0)
    }
  }
  return out
}

function loadPlaywright() {
  const candidates = [
    path.join(SCREENSHOTS_PKG, 'node_modules', 'playwright'),
    path.join(REPO_ROOT, 'node_modules', 'playwright'),
  ]
  for (const dir of candidates) {
    try {
      const require = createRequire(path.join(dir, 'package.json'))
      return require('playwright')
    } catch {
      /* next */
    }
  }
  try {
    const require = createRequire(path.join(SCREENSHOTS_PKG, 'package.json'))
    return require('playwright')
  } catch (err) {
    console.error('Playwright not found. Run: cd scripts/screenshots && npm install')
    throw err
  }
}

async function waitForUrl(url, { timeoutMs = 300_000, intervalMs = 2000 } = {}) {
  const start = Date.now()
  let lastErr = null
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) })
      if (res.ok || res.status === 304 || res.status === 401 || res.status === 403) return
      lastErr = new Error(`HTTP ${res.status}`)
    } catch (e) {
      lastErr = e
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error(`Timed out waiting for ${url}: ${lastErr?.message || lastErr}`)
}

function startStack() {
  console.log('  ▸ Starting full stack via ./scripts/everflow start …')
  const child = spawn('./scripts/everflow', ['start'], {
    cwd: REPO_ROOT,
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let log = ''
  const onData = (buf) => {
    log += buf.toString()
    if (process.env.VERBOSE === '1') process.stderr.write(buf)
  }
  child.stdout?.on('data', onData)
  child.stderr?.on('data', onData)
  return new Promise((resolve, reject) => {
    child.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`everflow start exited ${code}\n${log.slice(-2000)}`))
    })
  })
}

async function apiLogin(apiUrl, email, password) {
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch(`${apiUrl.replace(/\/$/, '')}/api/v1/auth/jwt/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok || !data.access_token) {
    throw new Error(`Login failed (${res.status}): ${data.detail || res.statusText}`)
  }
  return data.access_token
}

async function ensureAuth(page, opts) {
  if (opts.skipLogin) return
  if (!opts.email || !opts.password) {
    throw new Error(
      'Live capture requires credentials.\n' +
        '  Set EVERFLOW_EMAIL and EVERFLOW_PASSWORD\n' +
        '  (or EVERFLOW_ADMIN_EMAIL / EVERFLOW_ADMIN_PASSWORD)\n' +
        '  Create admin: ./scripts/everflow setup-admin',
    )
  }
  console.log(`  ▸ Logging in as ${opts.email} …`)
  const token = await apiLogin(opts.apiUrl, opts.email, opts.password)
  // Inject token before app boots so auth store sees session
  await page.addInitScript((t) => {
    localStorage.setItem('everflow_access_token', t)
  }, token)
  // If page already loaded, set and reload
  await page.evaluate((t) => {
    localStorage.setItem('everflow_access_token', t)
  }, token).catch(() => {})
  console.log('    ✓ token stored')
}

async function assertNoViteError(page) {
  const viteError = page.locator('vite-error-overlay')
  if ((await viteError.count().catch(() => 0)) > 0) {
    const text = await viteError.innerText().catch(() => '')
    throw new Error(`Unexpected Vite overlay (use live stack, not npm dev):\n${text.slice(0, 400)}`)
  }
}

async function dismissOverlays(page, { keepModals = false } = {}) {
  await assertNoViteError(page)
  // During intentional snaps (Create Project, etc.) do NOT close modals or Escape.
  if (keepModals) return
  for (const sel of [
    '[aria-label="Close"]',
    'button:has-text("Close")',
    'button:has-text("Skip")',
    'button:has-text("Cancel")',
    '.pf-v6-c-modal-box button[aria-label="Close"]',
  ]) {
    try {
      const el = page.locator(sel).first()
      if (await el.isVisible({ timeout: 250 }).catch(() => false)) {
        await el.click({ timeout: 800 }).catch(() => {})
      }
    } catch {
      /* ignore */
    }
  }
  await page.keyboard.press('Escape').catch(() => {})
}

async function waitForShell(page, { timeoutMs = 30_000 } = {}) {
  await page.waitForFunction(
    () => {
      const root = document.querySelector('#root') || document.body
      const t = (root?.innerText || '').trim()
      // Logged-in shell or still on auth form
      return t.length > 15
    },
    { timeout: timeoutMs },
  )
  await assertNoViteError(page)
}

async function gotoPath(page, baseUrl, p, settleMs) {
  const url = new URL(p, baseUrl).toString()
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90_000 })
  await page.waitForTimeout(settleMs)
  await dismissOverlays(page)
  await waitForShell(page)
  // If login modal still up, auth failed
  const loginTitle = page.getByText(/Sign in to Everflow/i)
  if (await loginTitle.isVisible({ timeout: 800 }).catch(() => false)) {
    throw new Error('Still on login screen — check credentials or setup-admin')
  }
}

function captionsPath(outDir) {
  return path.join(outDir, 'CAPTIONS.md')
}

function loadCaptions(outDir) {
  const p = captionsPath(outDir)
  if (!fs.existsSync(p)) return new Map()
  const map = new Map()
  const text = fs.readFileSync(p, 'utf8')
  // ### file.png\n\ncaption
  const re = /^###\s+(\S+)\s*\n+([\s\S]*?)(?=^###\s|\Z)/gm
  let m
  while ((m = re.exec(text))) {
    map.set(m[1].trim(), m[2].trim())
  }
  return map
}

function saveCaptions(outDir, map) {
  const lines = [
    '# Screenshot captions',
    '',
    'Generated for live Project Everflow captures. Used by the root README.',
    '',
  ]
  for (const [file, caption] of map) {
    lines.push(`### ${file}`, '', caption, '')
  }
  fs.writeFileSync(captionsPath(outDir), lines.join('\n'))
}

/** Resolve shot path under outDir; allows `playground/foo.png` subdirs. */
function resolveShotPath(outDir, filename, fallback = 'shot.png') {
  let n = (filename || fallback).trim() || fallback
  if (!n.endsWith('.png')) n += '.png'
  // normalize separators; block path escape
  n = n.replace(/\\/g, '/').replace(/^\/+/, '')
  const parts = n.split('/').filter((p) => p && p !== '..' && p !== '.')
  if (parts.length === 0) parts.push(fallback)
  const base = parts.pop()
  const safeBase = path.basename(base)
  const sub = parts.join('/')
  const destDir = sub ? path.join(outDir, sub) : outDir
  return { destDir, file: safeBase, relKey: sub ? `${sub}/${safeBase}` : safeBase }
}

async function takeSnap(page, outDir, filename, captions, caption, { fullPage = true } = {}) {
  // Never auto-dismiss modals on snap — Create Project / wizards must stay open
  await dismissOverlays(page, { keepModals: true })
  const { destDir, file, relKey } = resolveShotPath(outDir, filename)
  fs.mkdirSync(destDir, { recursive: true })
  const outPath = path.join(destDir, file)
  await page.screenshot({ path: outPath, fullPage })
  const st = fs.statSync(outPath)
  const rel = path.relative(REPO_ROOT, outPath)
  console.log(`  ✓ ${rel} (${Math.round(st.size / 1024)} KiB)`)
  if (caption) {
    captions.set(relKey, caption)
    saveCaptions(outDir, captions)
    console.log(`    caption: ${caption.slice(0, 100)}${caption.length > 100 ? '…' : ''}`)
  }
  return outPath
}

async function captureAppShots(page, opts, captions) {
  const written = []
  console.log('\n  ▸ App surfaces (live)\n')
  for (const shot of APP_SHOTS) {
    process.stdout.write(`  ▸ ${shot.name}… `)
    try {
      await gotoPath(page, opts.baseUrl, shot.path, opts.settleMs)
      await page.waitForTimeout(400)
      const outPath = await takeSnap(page, opts.outDir, shot.file, captions, shot.caption, {
        fullPage: opts.fullPage,
      })
      written.push(outPath)
    } catch (e) {
      console.log(`failed: ${e.message?.split('\n')[0] || e}`)
    }
  }
  return written
}

function cmdFilePath(outDir) {
  return path.join(outDir, '.capture-cmd')
}

async function runInteractive(page, opts, captions) {
  const cmdPath = cmdFilePath(opts.outDir)
  try {
    fs.unlinkSync(cmdPath)
  } catch {
    /* ok */
  }
  const pgDir = path.join(opts.outDir, 'playground')
  fs.mkdirSync(pgDir, { recursive: true })

  let lastFile = 'playground/feature.png'
  let done = false

  console.log(`
  ════════════════════════════════════════════════════════════
  LIVE INTERACTIVE MODE — full stack UI (not Vite demo)

  Base:  ${opts.baseUrl}
  Drive Playground: open a project, chat with agents, open
  Desktop / Code / Preview / etc. When the screen shows what
  you want:

    snap playground/chat-desktop.png Chat + live Desktop session
    caption More detail for the last shot…
    goto /marketplace
    quit

  Cmd file: ${path.relative(REPO_ROOT, cmdPath)}
  Captions: ${path.relative(REPO_ROOT, captionsPath(opts.outDir))}
  ════════════════════════════════════════════════════════════
`)

  const handleLine = async (line) => {
    const raw = String(line || '').trim()
    if (!raw) return
    const parts = raw.split(/\s+/)
    const cmd = parts[0].toLowerCase()
    try {
      if (cmd === 'quit' || cmd === 'q' || cmd === 'exit') {
        done = true
        return
      }
      if (cmd === 'snap' || cmd === 'shot' || cmd === 'capture') {
        // snap [file] [caption…]
        let file = parts[1] || lastFile
        let captionParts = parts.slice(2)
        // If second token doesn't look like a file, it's all caption
        if (file && !file.includes('.') && !file.includes('/') && !file.endsWith('png')) {
          captionParts = parts.slice(1)
          file = lastFile
        }
        if (!file.includes('/') && !file.startsWith('0') && !file.startsWith('playground')) {
          // default feature shots into playground/
          if (!/^\d/.test(file)) file = `playground/${file}`
        }
        const caption = captionParts.join(' ').trim() || captions.get(file) || ''
        lastFile = file.endsWith('.png') ? file : `${file}.png`
        await takeSnap(page, opts.outDir, lastFile, captions, caption || undefined, {
          fullPage: opts.fullPage,
        })
        return
      }
      if (cmd === 'caption') {
        const text = parts.slice(1).join(' ').trim()
        if (!text) {
          console.log('  ? usage: caption <text for last snap>')
          return
        }
        const key = lastFile.replace(/^docs\/screenshots\//, '')
        captions.set(key.includes('/') ? key : path.basename(key), text)
        // also try playground/ relative
        if (!key.includes('/')) captions.set(`playground/${key}`, text)
        saveCaptions(opts.outDir, captions)
        console.log(`  ✓ caption saved for ${lastFile}`)
        return
      }
      if (cmd === 'goto') {
        const p = parts[1] || '/'
        await gotoPath(page, opts.baseUrl, p, opts.settleMs)
        console.log(`  ✓ ${p}`)
        return
      }
      if (cmd === 'reload') {
        await page.reload({ waitUntil: 'domcontentloaded' })
        await page.waitForTimeout(600)
        await dismissOverlays(page)
        console.log('  ✓ reloaded')
        return
      }
      console.log('  ? commands: snap [file] [caption…] | caption <text> | goto /path | reload | quit')
    } catch (e) {
      console.error(`  ✗ ${e.message || e}`)
    }
  }

  let lastMtime = 0
  const poll = (async () => {
    while (!done) {
      try {
        const st = fs.statSync(cmdPath)
        if (st.mtimeMs > lastMtime) {
          lastMtime = st.mtimeMs
          const text = fs.readFileSync(cmdPath, 'utf8').trim()
          if (text) {
            console.log(`  ← ${text}`)
            await handleLine(text)
            try {
              fs.unlinkSync(cmdPath)
            } catch {
              /* ok */
            }
          }
        }
      } catch {
        /* no file */
      }
      await new Promise((r) => setTimeout(r, 400))
    }
  })()

  if (process.stdin.isTTY) {
    const rl = createInterface({ input: process.stdin, output: process.stdout, prompt: 'live> ' })
    rl.prompt()
    await new Promise((resolve) => {
      rl.on('line', async (line) => {
        await handleLine(line)
        if (done) {
          rl.close()
          resolve()
        } else rl.prompt()
      })
      rl.on('close', () => {
        done = true
        resolve()
      })
    })
  } else {
    console.log('  (no TTY — use docs/screenshots/.capture-cmd)')
    while (!done) {
      if (page.isClosed()) break
      await new Promise((r) => setTimeout(r, 500))
    }
  }
  done = true
  await poll.catch(() => {})
}

async function main() {
  const opts = parseArgs(process.argv.slice(2))
  opts.outDir = path.isAbsolute(opts.outDir)
    ? opts.outDir
    : path.resolve(REPO_ROOT, opts.outDir)

  console.log('\n  Everflow LIVE screenshot capture')
  console.log('  (full stack UI — not Vite / npm demo mode)')
  console.log(`  UI:        ${opts.baseUrl}`)
  console.log(`  API:       ${opts.apiUrl}`)
  console.log(`  Output:    ${opts.outDir}`)
  console.log(`  Mode:      ${opts.interactive ? 'interactive' : opts.appOnly ? 'app-only' : 'app + interactive'}`)
  console.log('')

  fs.mkdirSync(opts.outDir, { recursive: true })
  fs.mkdirSync(path.join(opts.outDir, 'playground'), { recursive: true })
  const captions = loadCaptions(opts.outDir)

  if (opts.startStack) {
    await startStack()
  }

  console.log('  ▸ Waiting for live UI …')
  await waitForUrl(opts.baseUrl, { timeoutMs: 300_000 })
  console.log('    ✓ UI reachable')
  console.log('  ▸ Waiting for API …')
  await waitForUrl(`${opts.apiUrl.replace(/\/$/, '')}/api/v1/health`, { timeoutMs: 180_000 })
  console.log('    ✓ API reachable')

  const { chromium } = loadPlaywright()
  const browser = await chromium.launch({
    headless: !opts.headed && !opts.interactive,
    args: opts.interactive ? ['--start-maximized'] : [],
  })

  const contextOpts = opts.interactive
    ? { viewport: null, colorScheme: 'light' }
    : {
        viewport: { width: opts.width, height: opts.height },
        deviceScaleFactor: 1,
        colorScheme: 'light',
      }

  const context = await browser.newContext(contextOpts)
  const page = await context.newPage()

  // Login token before first navigation
  if (!opts.skipLogin) {
    if (!opts.email || !opts.password) {
      await browser.close()
      throw new Error(
        'Set EVERFLOW_EMAIL and EVERFLOW_PASSWORD (run ./scripts/everflow setup-admin first).',
      )
    }
    const token = await apiLogin(opts.apiUrl, opts.email, opts.password)
    await context.addInitScript((t) => {
      localStorage.setItem('everflow_access_token', t)
    }, token)
    console.log(`  ▸ Authenticated as ${opts.email}`)
  }

  await page.goto(opts.baseUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 })
  await page.waitForTimeout(opts.settleMs)
  await dismissOverlays(page)
  await waitForShell(page)

  const written = []

  // Always capture app surfaces unless interactive-only with --interactive alone
  // User asked: basic places first, then playground interactive
  if (!opts.interactive || !process.argv.includes('--interactive-only')) {
    written.push(...(await captureAppShots(page, opts, captions)))
  }

  if (opts.interactive || (!opts.appOnly && process.argv.includes('--interactive'))) {
    await gotoPath(page, opts.baseUrl, '/', opts.settleMs)
    await runInteractive(page, opts, captions)
  } else if (!opts.appOnly && opts.interactive === false) {
    // Default batch ends after app shots; print next steps
    console.log(`
  App surfaces captured. For Playground (Desktop, live chat, …):

    EVERFLOW_EMAIL=… EVERFLOW_PASSWORD=… \\
      node scripts/capture-screenshots.mjs --interactive --headed

  Then open a project with a real sandbox, use Desktop + Chat, and:
    snap playground/desktop-ai.png Full desktop session driven by the agent
`)
  }

  await browser.close()
  console.log('\n  Captions file:', path.relative(REPO_ROOT, captionsPath(opts.outDir)))
  console.log('  Done.\n')
}

main().catch((err) => {
  console.error('\n  ✗', err.message || err)
  process.exit(1)
})
