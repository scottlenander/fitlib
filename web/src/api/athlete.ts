// The athlete history and year of birth.
import { useMutation, useQuery } from '@tanstack/react-query'
import { json, request, useInvalidate, type Schemas } from './client'

export type Athlete = Schemas['Athlete']
export type AthleteEntry = Schemas['AthleteEntryOut']
export type AthleteValues = Schemas['AthleteValuesIn']

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
