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
export type BulkMetaPatch = Schemas['BulkMetaPatch']
export type BulkMetaResult = Schemas['BulkMetaResult']
export type DeleteResult = Schemas['DeleteResult']
export type TagCount = Schemas['TagCount']
export type ZwiftWorld = Schemas['WorldOut']
export type SimilarRides = Schemas['SimilarRides']
export type SimilarRide = Schemas['SimilarRide']
export type Health = Schemas['Health']
export type TimeZoneChange = Schemas['TimeZoneChange']
export type Comparison = Schemas['Comparison']
export type ComparedRide = Schemas['ComparedRide']
export type Align = Comparison['align']
export type RouteProgress = Schemas['RouteProgress']
export type Span = Schemas['Span']
export type Volume = Schemas['Volume']
export type VolumeBucket = Schemas['VolumeBucketOut']
export type Fitness = Schemas['FitnessOut']
export type FitnessDay = Schemas['FitnessDayOut']
export type Ftp = Schemas['FtpOut']
export type Efficiency = Schemas['EfficiencyOut']
export type EfficiencyPoint = Schemas['EfficiencyPointOut']
export type BestCurve = Schemas['CurveOut']
export type CurveBest = Schemas['CurveBestOut']
export type WatchStatus = Schemas['WatchStatus']
export type WatchFolder = Schemas['WatchFolderOut']
export type WatchedFile = Schemas['WatchedFileOut']
export type ScanResult = Schemas['ScanOut']
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

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => request<Health>('/api/health') })
}

export function useSimilar(rideId: string, kind: 'route' | 'effort') {
  return useQuery({
    queryKey: ['similar', rideId, kind],
    queryFn: () =>
      request<SimilarRides>(
        `/api/rides/${encodeURIComponent(rideId)}/similar${queryString({ kind })}`,
      ),
  })
}

// Rides lined up for the compare page. `align` undefined lets the API choose.
export function useCompare(
  ids: string[],
  align: Align | undefined,
  smooth: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['compare', ids, align, smooth],
    queryFn: () => request<Comparison>(`/api/compare${queryString({ ids, align, smooth })}`),
    enabled,
    placeholderData: (previous) => previous,
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

// Imports files. Rides the user deleted are left out (and listed) unless `includeDeleted`.
export function useImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      files,
      includeDeleted = false,
    }: {
      files: File[]
      includeDeleted?: boolean
    }) => {
      const body = new FormData()
      for (const file of files) body.append('files', file)
      const query = includeDeleted ? '?include_deleted=true' : ''
      return request<ImportResult>(`/api/imports${query}`, { method: 'POST', body })
    },
    // New rides change every list.
    onSuccess: () =>
      Promise.all(
        ['rides', 'trends', 'route-progress'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
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

// The Zwift worlds the library can be filtered on.
export function useZwiftWorlds() {
  return useQuery({
    queryKey: ['zwift-worlds'],
    queryFn: () => request<ZwiftWorld[]>('/api/zwift-worlds'),
    staleTime: Infinity,
  })
}

export function useTags() {
  return useQuery({ queryKey: ['tags'], queryFn: () => request<TagCount[]>('/api/tags') })
}

export function useUpdateMeta(rideId: string) {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (patch: MetaPatch) =>
      request<RideDetail>(`/api/rides/${encodeURIComponent(rideId)}/meta`, json('PATCH', patch)),
    onSuccess: () => invalidate('ride', 'rides', 'tags', 'bikes', 'route-progress'),
  })
}

// Changes the effort, bike or tags of several rides at once (all of them, or none).
export function useBulkEdit() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (patch: BulkMetaPatch) =>
      request<BulkMetaResult>('/api/rides/bulk-meta', json('POST', patch)),
    onSuccess: () => invalidate('ride', 'rides', 'tags', 'bikes', 'route-progress'),
  })
}

// Deletes rides (all of them, or none), with their streams and original files. Their pages
// are dropped from the cache so nothing refetches a ride that's gone.
export function useDeleteRides() {
  const client = useQueryClient()
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (ids: string[]) => {
      const [only] = ids
      return ids.length === 1 && only !== undefined
        ? request<DeleteResult>(`/api/rides/${encodeURIComponent(only)}`, { method: 'DELETE' })
        : request<DeleteResult>('/api/rides/bulk-delete', json('POST', { ids }))
    },
    onSuccess: (_, ids) => {
      // Anything about a deleted ride (its page, similar rides, route progress, streams)
      // would only 404 and retry.
      const gone = new Set(ids)
      client.removeQueries({ predicate: (q) => q.queryKey.some((k) => gone.has(k as string)) })
      // Not awaited: the caller moves on while lists refresh.
      void invalidate(
        'rides',
        'tags',
        'bikes',
        'trends',
        'route-progress',
        'similar',
        'compare',
        'watch',
        'athlete',
      )
    },
  })
}

// The time zones the default can be set to (IANA names, from the server's database).
export function useTimeZones() {
  return useQuery({
    queryKey: ['time-zones'],
    queryFn: () => request<string[]>('/api/settings/time-zones'),
    staleTime: Infinity,
  })
}

// Changes the default time zone; rides that follow it change date and time.
export function useSetTimeZone() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (timezone: string | null) =>
      request<TimeZoneChange>('/api/settings/timezone', json('PUT', { timezone })),
    onSuccess: () =>
      invalidate('settings', 'ride', 'rides', 'similar', 'compare', 'trends', 'route-progress'),
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
    onSuccess: () =>
      invalidate('athlete', 'ride', 'rides', 'trends', 'route-progress', 'compare', 'similar'),
  })
}

// Sets or clears the year of birth, which threshold heart rate is estimated from.
export function useSetBirthYear() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (year: number | null) =>
      request<Athlete>('/api/athlete/birth-year', json('PUT', { birth_year: year })),
    onSuccess: () =>
      invalidate('athlete', 'ride', 'rides', 'trends', 'route-progress', 'compare', 'similar'),
  })
}

export function useDeleteAthlete() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (from: string) => request<void>(`/api/athlete/${from}`, { method: 'DELETE' }),
    onSuccess: () =>
      invalidate('athlete', 'ride', 'rides', 'trends', 'route-progress', 'compare', 'similar'),
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

export function useRouteProgress(rideId: string) {
  return useQuery({
    queryKey: ['route-progress', rideId],
    queryFn: () =>
      request<RouteProgress>(`/api/rides/${encodeURIComponent(rideId)}/route-progress`),
  })
}

// Trends. Each takes local dates (YYYY-MM-DD); the previous answer stays on screen while a
// new range loads.
type Range = { since: string; until: string }

function trend<T>(path: string, params: Record<string, string>, enabled = true) {
  return {
    queryKey: ['trends', path, params],
    queryFn: () => request<T>(`/api/trends/${path}${queryString(params)}`),
    placeholderData: (previous: T | undefined) => previous,
    enabled,
  }
}

export function useTrendSpan() {
  return useQuery({
    queryKey: ['trends', 'span'],
    queryFn: () => request<Span>('/api/trends/span'),
  })
}

export function useVolume(range: Range, period: 'week' | 'month', enabled: boolean) {
  return useQuery(trend<Volume>('volume', { ...range, period }, enabled))
}

export function useFitness(range: Range, enabled: boolean) {
  return useQuery(trend<Fitness>('fitness', range, enabled))
}

export function useFtp(range: Range, period: 'week' | 'month', enabled: boolean) {
  return useQuery(trend<Ftp>('ftp', { ...range, period }, enabled))
}

export function useEfficiency(range: Range, enabled: boolean) {
  return useQuery(trend<Efficiency>('efficiency', range, enabled))
}

export function useBestCurve(range: Range, kind: 'power' | 'hr', enabled: boolean) {
  return useQuery(trend<BestCurve>('curve', { ...range, kind }, enabled))
}

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

// Everything a newly imported ride can change.
export const NEW_RIDE_KEYS = [
  'rides',
  'ride',
  'trends',
  'route-progress',
  'similar',
  'tags',
  'health',
]

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
