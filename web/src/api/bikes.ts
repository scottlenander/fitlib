// Bikes, the default-bike timeline and backfill.
import { useMutation, useQuery } from '@tanstack/react-query'
import { json, queryString, request, useInvalidate, type Schemas } from './client'

export type BikeKind = Schemas['BikeKind']
export type BikeSlot = Schemas['BikeSlot']
export type BikeWithTotals = Schemas['BikeWithTotals']
export type BikeOut = Schemas['BikeOut']
export type BikePatch = Schemas['BikePatch']
export type DefaultEntry = Schemas['DefaultOut']
export type BackfillResult = Schemas['BackfillResult']

export function useBikes() {
  return useQuery({
    queryKey: ['bikes'],
    queryFn: () => request<BikeWithTotals[]>('/api/bikes'),
  })
}

export function useAddBike() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (bike: { name: string; kind: BikeKind | null }) =>
      request<BikeOut>('/api/bikes', json('POST', bike)),
    onSuccess: () => invalidate('bikes'),
  })
}

export function useUpdateBike() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: BikePatch }) =>
      request<BikeOut>(`/api/bikes/${encodeURIComponent(id)}`, json('PATCH', patch)),
    onSuccess: () => invalidate('bikes', 'defaults', 'ride', 'rides'),
  })
}

export function useDefaults() {
  return useQuery({
    queryKey: ['defaults'],
    queryFn: () => request<DefaultEntry[]>('/api/bikes/defaults'),
  })
}

export function useSetDefault() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ slot, from, bikeId }: { slot: BikeSlot; from: string; bikeId: string | null }) =>
      request<DefaultEntry>(
        `/api/bikes/defaults/${slot}/${from}`,
        json('PUT', { bike_id: bikeId }),
      ),
    onSuccess: () => invalidate('defaults'),
  })
}

export function useDeleteDefault() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ slot, from }: { slot: BikeSlot; from: string }) =>
      request<void>(`/api/bikes/defaults/${slot}/${from}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('defaults'),
  })
}

export function useBackfill() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (dryRun: boolean) =>
      request<BackfillResult>(`/api/bikes/backfill${queryString({ dry_run: dryRun })}`, {
        method: 'POST',
      }),
    onSuccess: (result) => {
      if (!result.dry_run) void invalidate('bikes', 'ride', 'rides')
    },
  })
}
