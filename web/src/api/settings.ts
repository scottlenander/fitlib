// Library settings, time zones, the server's health and the Zwift worlds.
import { useMutation, useQuery } from '@tanstack/react-query'
import { json, request, useInvalidate, type Schemas } from './client'

export type Settings = Schemas['Settings']
export type ZwiftWorld = Schemas['WorldOut']
export type Health = Schemas['Health']
export type TimeZoneChange = Schemas['TimeZoneChange']

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: () => request<Settings>('/api/settings'),
    staleTime: Infinity,
  })
}

// How often to ask again while the server recomputes rides, for the progress.
export const RECOMPUTE_POLL_MS = 2000

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => request<Health>('/api/health'),
    refetchInterval: (query) => (query.state.data?.recompute ? RECOMPUTE_POLL_MS : false),
  })
}

// The Zwift worlds the library can be filtered on.
export function useZwiftWorlds() {
  return useQuery({
    queryKey: ['zwift-worlds'],
    queryFn: () => request<ZwiftWorld[]>('/api/zwift-worlds'),
    staleTime: Infinity,
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
