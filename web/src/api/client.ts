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
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

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
