import type { EmbedStatus, KnowledgeCanvas, KnowledgeOrigin } from '@/types/studio'

export type StatusTone = 'neutral' | 'ok' | 'warn' | 'info' | 'danger'

const BUSY: EmbedStatus[] = ['uploading', 'ocr', 'chunking', 'embedding']

export function isPipelineBusy(status: EmbedStatus): boolean {
  return BUSY.includes(status)
}

/** How the canvas was created — omit for ordinary manual notes. */
export function kindLabel(origin: KnowledgeOrigin): string | null {
  switch (origin) {
    case 'ocr':
      return 'From PDF (OCR)'
    case 'upload':
      return 'Uploaded file'
    case 'web':
      return 'From web'
    case 'repo':
      return 'From repo'
    case 'research':
      return 'From research'
    case 'created':
    default:
      return null
  }
}

/** Whether the chatbot can retrieve this canvas (user-facing). */
export function chatKnowledgeLabel(
  status: EmbedStatus,
  opts?: { bodyDirty?: boolean },
): { label: string; tone: StatusTone } {
  if (isPipelineBusy(status)) {
    const step =
      status === 'ocr'
        ? 'OCR'
        : status === 'uploading'
          ? 'upload'
          : status === 'chunking'
            ? 'chunking'
            : 'embedding'
    return { label: `Preparing (${step})…`, tone: 'info' }
  }
  if (status === 'error') {
    return { label: 'Failed', tone: 'danger' }
  }
  if (status === 'stale' || (status === 'indexed' && opts?.bodyDirty)) {
    return { label: 'Needs re-index', tone: 'warn' }
  }
  if (status === 'indexed') {
    return { label: 'In chatbot knowledge', tone: 'ok' }
  }
  // ready (and any legacy idle)
  return { label: 'Notes only', tone: 'neutral' }
}

/** Sidebar secondary line: kind + knowledge, compact. */
export function sidebarMetaLine(
  canvas: KnowledgeCanvas,
  opts?: { unsaved?: boolean; bodyDirty?: boolean },
): string {
  const parts: string[] = []
  const kind = kindLabel(canvas.origin)
  if (kind) parts.push(kind)

  if (isPipelineBusy(canvas.status)) {
    parts.push(chatKnowledgeLabel(canvas.status).label)
  } else {
    parts.push(chatKnowledgeLabel(canvas.status, { bodyDirty: opts?.bodyDirty }).label)
  }

  if (opts?.unsaved) parts.push('Unsaved')
  return parts.join(' · ')
}

export function knowledgeActionLabel(status: EmbedStatus): string {
  if (status === 'indexed') return 'Re-index'
  if (status === 'stale') return 'Update'
  return 'Index'
}

export function statusToneColor(
  tone: StatusTone,
): 'green' | 'blue' | 'orange' | 'red' | 'grey' {
  switch (tone) {
    case 'ok':
      return 'green'
    case 'warn':
      return 'orange'
    case 'info':
      return 'blue'
    case 'danger':
      return 'red'
    default:
      return 'grey'
  }
}
