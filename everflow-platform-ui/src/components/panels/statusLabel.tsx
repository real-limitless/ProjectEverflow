import { Label } from '@patternfly/react-core'

export function statusColor(
  s: string,
): 'green' | 'blue' | 'orange' | 'red' | 'grey' {
  if (s === 'ok' || s === 'done') return 'green'
  if (s === 'run' || s === 'running') return 'blue'
  if (s === 'warn' || s === 'warning') return 'orange'
  if (s === 'err' || s === 'error' || s === 'failed') return 'red'
  return 'grey'
}

export function StatusLabel({ status, text }: { status: string; text?: string }) {
  return (
    <Label color={statusColor(status)}>
      {text ?? status}
    </Label>
  )
}
