// Trends. Each takes local dates (YYYY-MM-DD); the previous answer stays on screen while a
// new range loads.
import { useQuery } from '@tanstack/react-query'
import { queryString, request, type Schemas } from './client'

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
