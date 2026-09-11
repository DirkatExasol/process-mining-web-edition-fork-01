import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { IntegrationApp } from './IntegrationApp'
import './styles.css'

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <IntegrationApp />
  </StrictMode>,
)
