// Typed calls to the fitlib API (types generated from its OpenAPI description by
// `npm run api:types`), and the TanStack Query hooks the pages use.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components, operations } from './schema'

type Schemas = components['schemas']
export type RideItem = Schemas['RideItem']
export type RidePage = Schemas['RidePage']
export type RideDetail = Schemas['RideDetail']
export type Streams = Schemas['Streams']
export type ImportResult = Schemas['ImportResult']
export type Settings = Schemas['Settings']
export type ZoneTime = Schemas['ZoneTime']
export type CurvePoint = Schemas['CurvePoint']
export type SortKey = Schemas['SortKey']
export type Athlete = Schemas['Athlete']
export type AthleteEntry = Schemas['AthleteEntryOut']
export type AthleteValues = Schemas['AthleteValuesIn']
export type BikeKind = Schemas['BikeKind']
export type BikeSlot = Schemas['BikeSlot']
export type BikeWithTotals = Schemas['BikeWithTotals']
export type BikeOut = Schemas['BikeOut']
export type BikePatch = Schemas['BikePatch']
export type DefaultEntry = Schemas['DefaultOut']
export type BackfillResult = Schemas['BackfillResult']
export type MetaPatch = Schemas['MetaPatch']
export type TagCount = Schemas['TagCount']
export type RideQuery = NonNullable<operations['list_rides_api_rides_get']['parameters']['query']>

// An error from the API, with its status and message.
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
      // Validation errors: a list of problems, each with a message.
      else if (Array.isArray(body.detail))
        message = body.detail
          .map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, ''))
          .join('; ')
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

// Builds a query string, repeating keys for arrays and leaving out empty values.
export function queryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    for (const item of Array.isArray(value) ? value : [value]) search.append(key, String(item))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => request<Settings>('/api/settings'),
    staleTime: Infinity,
  })
}

export function useRides(query: RideQuery) {
  return useQuery({
    queryKey: ['rides', query],
    queryFn: () => request<RidePage>(`/api/rides${queryString(query)}`),
    placeholderData: (previous) => previous,
  })
}

export function useRide(ref: string) {
  return useQuery({
    queryKey: ['ride', ref],
    queryFn: () => request<RideDetail>(`/api/rides/${encodeURIComponent(ref)}`),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  })
}

export function useStreams(rideId: string, fields: string[], step: number, enabled: boolean) {
  return useQuery({
    queryKey: ['streams', rideId, fields, step],
    queryFn: () =>
      request<Streams>(
        `/api/rides/${encodeURIComponent(rideId)}/streams${queryString({ fields, step })}`,
      ),
    enabled,
    staleTime: Infinity,
  })
}

export function useImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => {
      const body = new FormData()
      for (const file of files) body.append('files', file)
      return request<ImportResult>('/api/imports', { method: 'POST', body })
    },
    // New rides change every list.
    onSuccess: () => client.invalidateQueries({ queryKey: ['rides'] }),
  })
}

// -- writes ---------------------------------------------------------------------------------
// Each change refreshes whatever it can affect: a bike or FTP change alters ride lists and
// ride pages, so those are refetched too.

function useInvalidate() {
  const client = useQueryClient()
  return (...keys: string[]) =>
    Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key] })))
}

export function useTags() {
  return useQuery({ queryKey: ['tags'], queryFn: () => request<TagCount[]>('/api/tags') })
}

export function useUpdateMeta(rideId: string) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (patch: MetaPatch) =>
      request<RideDetail>(`/api/rides/${encodeURIComponent(rideId)}/meta`, json('PATCH', patch)),
    onSuccess: () => invalidate('ride', 'rides', 'tags', 'bikes'),
  })
}

export function useAthlete() {
  return useQuery({ queryKey: ['athlete'], queryFn: () => request<Athlete>('/api/athlete') })
}

export function useSetAthlete() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ from, values }: { from: string; values: AthleteValues }) =>
      request<AthleteEntry>(`/api/athlete/${from}`, json('PUT', values)),
    onSuccess: () => invalidate('athlete', 'ride', 'rides'),
  })
}

export function useDeleteAthlete() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (from: string) => request<void>(`/api/athlete/${from}`, { method: 'DELETE' }),
    onSuccess: () => invalidate('athlete', 'ride', 'rides'),
  })
}

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
