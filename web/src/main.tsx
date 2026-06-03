// Cesium config MUST be first — sets CESIUM_BASE_URL before any cesium import
import './cesium-config'

// i18n must initialise before any component renders (so useTranslation
// doesn't return keys on first paint).
import './i18n'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
