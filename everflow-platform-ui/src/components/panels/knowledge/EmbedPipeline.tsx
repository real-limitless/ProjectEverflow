import type { EmbedStatus } from '@/types/studio'
import { isPipelineBusy } from './canvasStatus'

const DEFAULT_STEPS: EmbedStatus[] = ['uploading', 'chunking', 'embedding', 'indexed']
const OCR_STEPS: EmbedStatus[] = ['uploading', 'ocr', 'chunking', 'embedding', 'indexed']

const LABELS: Partial<Record<EmbedStatus, string>> = {
  uploading: 'uploading',
  ocr: 'unlimited ocr',
  chunking: 'chunking',
  embedding: 'embedding',
  indexed: 'done',
}

export function EmbedPipeline({
  status,
  withOcr = false,
}: {
  status: EmbedStatus
  withOcr?: boolean
}) {
  if (!isPipelineBusy(status)) {
    return null
  }

  const steps = withOcr || status === 'ocr' ? OCR_STEPS : DEFAULT_STEPS
  const active = status === 'error' ? 'uploading' : status === 'indexed' ? 'indexed' : status
  const found = steps.indexOf(active as EmbedStatus)
  const idx = found < 0 ? 0 : found

  return (
    <div className="embed-pipeline" aria-label="Knowledge preparation pipeline">
      {steps.map((step, i) => (
        <span
          key={step}
          className={`embed-step ${i < idx ? 'is-done' : i === idx ? 'is-active' : ''}`}
        >
          {LABELS[step] ?? step}
        </span>
      ))}
    </div>
  )
}
