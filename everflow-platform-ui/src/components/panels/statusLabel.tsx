import { Label } from '@patternfly/react-core'

export function statusColor(
  s: string,
): 'green' | 'blue' | 'orange' | 'red' | 'grey' {
  if (s === 'ok' || s === 'done' || s === 'passed' || s === 'online') return 'green'
  if (s === 'run' || s === 'running' || s === 'queued') return 'blue'
  if (s === 'warn' || s === 'warning' || s === 'cancelled') return 'orange'
  if (s === 'err' || s === 'error' || s === 'failed' || s === 'offline') return 'red'
  return 'grey'
}

export function StatusLabel({ status, text }: { status: string; text?: string }) {
  return (
    <Label color={statusColor(status)}>
      {text ?? status}
    </Label>
  )
}
