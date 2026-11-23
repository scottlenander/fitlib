import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { App } from './App'
import { shouldRetry } from './api/client'
import './styles.css'
import { ThemeProvider } from './theme'
import { UnitsProvider } from './units'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: shouldRetry },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <UnitsProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </UnitsProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
