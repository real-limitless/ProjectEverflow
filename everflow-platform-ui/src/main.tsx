import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@patternfly/react-core/dist/styles/base.css'
import './styles/playground.css'
import './styles/app.css'
import './styles/chat.css'
import './styles/studio-panels.css'
import './styles/room-chart.css'
import { applyThemeClass, loadTheme } from '@/lib/namedLayouts'
import App from './App'

// Avoid flash of wrong theme
applyThemeClass(loadTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
