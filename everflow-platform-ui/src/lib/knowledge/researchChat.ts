/**
 * Ephemeral OpenCode sessions for Knowledge web reader (summarize + research chat).
 * Not listed in the main Chat panel conversation list.
 */

import {
  createSession,
  deleteSession,
  ensureOpenCode,
  listProviders,
  promptSync,
} from '@/lib/opencode/client'
import type { OcMessageBundle, OcPart } from '@/lib/opencode/types'

const MAX_ARTICLE_CHARS = 48_000

function extractAssistantText(bundle: OcMessageBundle | null | undefined): string {
  if (!bundle?.parts?.length) return ''
  const chunks: string[] = []
  for (const p of bundle.parts as OcPart[]) {
    if (p.type === 'text' || p.type === 'reasoning') {
      const t = (p.text || p.content || '').trim()
      if (t) chunks.push(t)
    }
  }
  return chunks.join('\n\n').trim()
}

async function pickModel(
  projectId: string,
): Promise<{ providerID: string; modelID: string } | undefined> {
  try {
    const cfg = await listProviders(projectId)
    const defaults = cfg.default || {}
    // Prefer connected providers
    const connected = new Set(cfg.connected || [])
    const providers = cfg.providers || []
    const ordered = [
      ...providers.filter((p) => connected.has(p.id)),
      ...providers.filter((p) => !connected.has(p.id)),
    ]
    for (const p of ordered) {
      const defId = defaults[p.id]
      const models = (p as { models?: Record<string, unknown> | Array<{ id?: string }> }).models
      let modelID: string | undefined = defId
      if (!modelID && models) {
        if (Array.isArray(models)) {
          modelID = models[0]?.id
        } else {
          modelID = Object.keys(models)[0]
        }
      }
      if (modelID) return { providerID: p.id, modelID }
    }
  } catch {
    /* optional */
  }
  return undefined
}

function articleSystem(articleTitle: string, articleMarkdown: string): string {
  const body = (articleMarkdown || '').slice(0, MAX_ARTICLE_CHARS)
  return [
    'You are a research assistant helping a developer understand a web article.',
    'Use only the article content below unless the user clearly asks for general knowledge.',
    'Be concise and practical. Use markdown when helpful.',
    'Do not claim you browsed the live site; you only have this extracted text.',
    '',
    `Article title: ${articleTitle}`,
    '',
    '--- ARTICLE START ---',
    body,
    '--- ARTICLE END ---',
  ].join('\n')
}

/** Deny all tool wildcards so research stays read-only text. */
const RESEARCH_TOOLS: Record<string, boolean> = {
  '*': false,
}

export async function summarizeArticleWithOpenCode(
  projectId: string,
  articleTitle: string,
  articleMarkdown: string,
): Promise<string> {
  await ensureOpenCode(projectId)
  const model = await pickModel(projectId)
  const session = await createSession(projectId, `Summarize · ${articleTitle.slice(0, 80)}`)
  try {
    const bundle = await promptSync(projectId, session.id, {
      parts: [
        {
          type: 'text',
          text: 'Summarize this article for a developer. Cover: purpose, key points, practical steps, and anything relevant to building or operating software. Keep it under ~200 words.',
        },
      ],
      model,
      system: articleSystem(articleTitle, articleMarkdown),
      tools: RESEARCH_TOOLS,
    })
    const text = extractAssistantText(bundle)
    if (!text) throw new Error('Empty summary from model')
    return text
  } finally {
    try {
      await deleteSession(projectId, session.id)
    } catch {
      /* ignore */
    }
  }
}

export type ResearchSession = {
  sessionId: string
}

export async function startResearchSession(
  projectId: string,
  articleTitle: string,
): Promise<ResearchSession> {
  await ensureOpenCode(projectId)
  const session = await createSession(projectId, `Research · ${articleTitle.slice(0, 80)}`)
  return { sessionId: session.id }
}

export async function researchChatTurn(
  projectId: string,
  sessionId: string,
  articleTitle: string,
  articleMarkdown: string,
  userMessage: string,
): Promise<string> {
  const model = await pickModel(projectId)
  const bundle = await promptSync(projectId, sessionId, {
    parts: [{ type: 'text', text: userMessage }],
    model,
    system: articleSystem(articleTitle, articleMarkdown),
    tools: RESEARCH_TOOLS,
  })
  const text = extractAssistantText(bundle)
  if (!text) throw new Error('Empty reply from model')
  return text
}

export async function endResearchSession(projectId: string, sessionId: string): Promise<void> {
  try {
    await deleteSession(projectId, sessionId)
  } catch {
    /* ignore */
  }
}
