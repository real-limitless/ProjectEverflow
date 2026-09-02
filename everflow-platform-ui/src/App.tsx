import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { MarketplacePage } from '@/pages/MarketplacePage'
import { MarketplaceDetailPage } from '@/pages/MarketplaceDetailPage'
import { UsagePage } from '@/pages/UsagePage'
import { HarnessesPage } from '@/pages/HarnessesPage'
import { DetachedPanelPage } from '@/pages/DetachedPanelPage'
import { StudioToastHost } from '@/components/studio/StudioToastHost'

function AppRoutes() {
  const [params] = useSearchParams()
  const detach = params.get('detach')

  if (detach) {
    return (
      <Routes>
        <Route element={<AppShell detached />}>
          <Route path="*" element={<DetachedPanelPage />} />
        </Route>
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<PlaygroundPage />} />
        <Route path="overview" element={<Navigate to="/" replace />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="marketplace" element={<MarketplacePage />} />
        <Route path="marketplace/:kind/:itemId" element={<MarketplaceDetailPage />} />
        <Route path="harnesses" element={<HarnessesPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
      <StudioToastHost />
    </BrowserRouter>
  )
}
