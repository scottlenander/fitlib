// Watched folders. The status is polled while the tab is visible (TanStack Query pauses the
// interval in a hidden tab), so new rides from the server's watcher show up without a
// reload; with several pages asking, the shortest interval wins.
import { useMutation, useQuery } from '@tanstack/react-query'
import { NEW_RIDE_KEYS, json, queryString, request, useInvalidate, type Schemas } from './client'

export type WatchStatus = Schemas['WatchStatus']
export type WatchFolder = Schemas['WatchFolderOut']
export type WatchedFile = Schemas['WatchedFileOut']
export type ScanResult = Schemas['ScanOut']

// Watched folders. The status is polled while the tab is visible (TanStack Query pauses the
// interval in a hidden tab), so new rides from the server's watcher show up without a
// reload; with several pages asking, the shortest interval wins.
export const WATCH_POLL_MS = 15_000

export function useWatch(pollMs = WATCH_POLL_MS) {
  return useQuery({
    queryKey: ['watch'],
    queryFn: () => request<WatchStatus>('/api/watch'),
    refetchInterval: pollMs,
  })
}

export function useAddWatchFolder() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (path: string) =>
      request<WatchFolder>('/api/watch/folders', json('POST', { path })),
    onSuccess: () => invalidate('watch'),
  })
}

export function useRemoveWatchFolder() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (path: string) =>
      request<void>(`/api/watch/folders${queryString({ path })}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('watch'),
  })
}

export function useScanWatched() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: () => request<ScanResult>('/api/watch/scan', { method: 'POST' }),
    // Without the server's watcher, the scan has imported rides by the time it answers.
    onSuccess: (result) => invalidate('watch', ...(result.background ? [] : NEW_RIDE_KEYS)),
  })
}
