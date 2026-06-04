// Cesium config MUST be first — sets CESIUM_BASE_URL before any cesium import
import './cesium-config'

// i18n must initialise before any component renders (so useTranslation
// doesn't return keys on first paint).
import './i18n'

// Observability (Sentry + Plausible) — runs BEFORE React mounts so a
// crash during initial render is still captured. Both are no-ops
// unless their env vars are set; see web/DEPLOY.md.
import { initObservability } from './observability'
initObservability()

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/globals.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
