import { useEffect, useState } from 'react'
import { Alert, AlertActionCloseButton, AlertGroup } from '@patternfly/react-core'
import { dismissToast, subscribeToasts, type StudioToast } from '@/lib/studioToast'

export function StudioToastHost() {
  const [toasts, setToasts] = useState<StudioToast[]>([])

  useEffect(() => subscribeToasts(setToasts), [])

  if (!toasts.length) return null

  return (
    <AlertGroup isToast isLiveRegion className="studio-toast-host">
      {toasts.map((t) => (
        <Alert
          key={t.id}
          variant={t.kind === 'danger' ? 'danger' : t.kind === 'warning' ? 'warning' : t.kind === 'success' ? 'success' : 'info'}
          title={t.title}
          timeout={false}
          actionClose={<AlertActionCloseButton onClose={() => dismissToast(t.id)} />}
        >
          {t.description}
        </Alert>
      ))}
    </AlertGroup>
  )
}
