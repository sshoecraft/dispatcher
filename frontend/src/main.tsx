import { createRoot } from 'react-dom/client'
import { StrictMode } from 'react'
import { BrowserRouter } from 'react-router'

import AppRoutes from '@/app/routes'
import { loadConfig } from '@/config'
import { setApiBase } from '@/lib/api'

import '@/styles/index.css'
import { ConfigProvider, ThemeProvider } from '@/contexts'

loadConfig().then((config) => {
  setApiBase(config.API_URL)
  document.title = config.htmlTitle
  document.documentElement.style.setProperty(
    '--color-primary-blue',
    config.primaryColor
  )

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ConfigProvider config={config}>
        <ThemeProvider>
          <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
            <AppRoutes />
          </BrowserRouter>
        </ThemeProvider>
      </ConfigProvider>
    </StrictMode>
  )
})
