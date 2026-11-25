// Comparing rides.
import { useQuery } from '@tanstack/react-query'
import { ApiError, queryString, request, type Schemas } from './client'

export type Comparison = Schemas['Comparison']
export type ComparedRide = Schemas['ComparedRide']
export type Align = Comparison['align']

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
