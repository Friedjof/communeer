import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useThemeEffect } from '@/hooks/useThemeEffect'
import { ErrorBoundary } from './ErrorBoundary'
import { queryClient } from './queryClient'
import { router } from './router'

export function App() {
  useThemeEffect()

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
