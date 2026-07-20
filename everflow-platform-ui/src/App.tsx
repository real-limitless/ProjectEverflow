import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { PlaygroundPage } from '@/pages/PlaygroundPage'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { DetachedPanelPage } from '@/pages/DetachedPanelPage'

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
        <Route
          path="overview"
          element={
            <PlaceholderPage
              title="Overview"
              description="Org dashboard, nodes, and project health will live here."
            />
          }
        />
        <Route path="usage" element={<PlaceholderPage title="Usage" />} />
        <Route path="plans" element={<PlaceholderPage title="Plans & Billing" />} />
        <Route path="harnesses" element={<PlaceholderPage title="Harnesses" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
