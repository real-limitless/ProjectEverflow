/** Lightweight toast bus for studio demo panels (no external toast lib). */

export type ToastKind = 'info' | 'success' | 'warning' | 'danger'

export interface StudioToast {
  id: string
  title: string
  description?: string
  kind: ToastKind
}

type Listener = (toasts: StudioToast[]) => void

let toasts: StudioToast[] = []
const listeners = new Set<Listener>()

function emit() {
  listeners.forEach((l) => l(toasts))
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener)
  listener(toasts)
  return () => listeners.delete(listener)
}

export function pushToast(title: string, opts?: { description?: string; kind?: ToastKind; ms?: number }) {
  const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const toast: StudioToast = {
    id,
    title,
    description: opts?.description,
    kind: opts?.kind ?? 'info',
  }
  toasts = [...toasts, toast]
  emit()
  const ms = opts?.ms ?? 3200
  window.setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  }, ms)
}

export function dismissToast(id: string) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}
