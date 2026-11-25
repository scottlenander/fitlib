// The server itself: stopping it from the Quit button.
import { useMutation } from '@tanstack/react-query'
import { request, type Schemas } from './client'

export type Stopping = Schemas['Stopping']

// Asks the server to stop (only offered when health's can_quit is true).
export function useQuitServer() {
  return useMutation({
    mutationFn: () => request<Stopping>('/api/app/quit', { method: 'POST' }),
  })
}
