// Rides: the list, one ride, its samples, map, similar rides and route progress, tags, and
// editing and deleting rides.
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import type { operations } from './schema'
import { ApiError, json, queryString, request, useInvalidate, type Schemas } from './client'

export type RideItem = Schemas['RideItem']
export type RidePage = Schemas['RidePage']
export type RideDetail = Schemas['RideDetail']
export type Streams = Schemas['Streams']
export type ZoneTime = Schemas['ZoneTime']
export type CurvePoint = Schemas['CurvePoint']
export type SortKey = Schemas['SortKey']
export type MetaPatch = Schemas['MetaPatch']
export type BulkMetaPatch = Schemas['BulkMetaPatch']
export type BulkMetaResult = Schemas['BulkMetaResult']
export type DeleteResult = Schemas['DeleteResult']
export type TagCount = Schemas['TagCount']
export type SimilarRides = Schemas['SimilarRides']
export type SimilarRide = Schemas['SimilarRide']
export type RouteProgress = Schemas['RouteProgress']
export type RideMap = Schemas['RideMap']
export type MapPoint = Schemas['MapPoint']
export type RideQuery = NonNullable<operations['list_rides_api_rides_get']['parameters']['query']>

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

export function useSimilar(rideId: string, kind: 'route' | 'effort') {
  return useQuery({
    queryKey: ['similar', rideId, kind],
    queryFn: () =>
      request<SimilarRides>(
        `/api/rides/${encodeURIComponent(rideId)}/similar${queryString({ kind })}`,
      ),
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
    // Always the bulk endpoint, even for one ride: it lists rides already gone.
    mutationFn: (ids: string[]) =>
      request<DeleteResult>('/api/rides/bulk-delete', json('POST', { ids })),
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

// A ride's route for the map (no points for rides without positions).
export function useRideMap(rideId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['map', rideId],
    queryFn: () => request<RideMap>(`/api/rides/${encodeURIComponent(rideId)}/map`),
    enabled,
    staleTime: Infinity,
  })
}

// Several rides' routes for one map (compare).
export function useRideMaps(rideIds: string[]) {
  return useQueries({
    queries: rideIds.map((id) => ({
      queryKey: ['map', id],
      queryFn: () => request<RideMap>(`/api/rides/${encodeURIComponent(id)}/map`),
      staleTime: Infinity,
    })),
  })
}

export function useRouteProgress(rideId: string) {
  return useQuery({
    queryKey: ['route-progress', rideId],
    queryFn: () =>
      request<RouteProgress>(`/api/rides/${encodeURIComponent(rideId)}/route-progress`),
  })
}
