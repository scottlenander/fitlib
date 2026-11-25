// The API's core: requests, errors and query strings. Types and hooks for each resource are in
// the modules beside this one (rides, bikes, trends...), generated types in ./schema.
import { useQueryClient } from '@tanstack/react-query'
import type { components } from './schema'

export type Schemas = components['schemas']

// An error from the API, with its status and message, and for several rides asked for at
// once, the ones no longer in the library.
export class ApiError extends Error {
  readonly status: number
  readonly missing: string[]

  constructor(status: number, message: string, missing: string[] = []) {
    super(message)
    this.status = status
    this.missing = missing
  }
}

// The rides an error says are no longer in the library (none for other errors).
export function missingRides(error: unknown): string[] {
  return error instanceof ApiError ? error.missing : []
}

// Whether a failed query is worth trying again: not when the server answered that the
// request itself was wrong (a 4xx, such as a ride that's gone), only for network or server
// trouble.
export function shouldRetry(failures: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false
  return failures < 3
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = response.statusText
    let missing: string[] = []
    try {
      const body = (await response.json()) as { detail?: unknown; missing?: unknown }
      if (Array.isArray(body.missing))
        missing = body.missing.filter((m): m is string => typeof m === 'string')
      if (typeof body.detail === 'string') message = body.detail
      // Validation errors: a list of problems, each with a message.
      else if (Array.isArray(body.detail))
        message = body.detail
          .map((d: { msg?: string }) => (d.msg ?? '').replace(/^Value error, /, ''))
          .join('; ')
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(response.status, message, missing)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const json = (method: string, body: unknown): RequestInit => ({
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

// Each change refreshes whatever it can affect: a bike or FTP change alters ride lists and
// ride pages, so those are refetched too.
export function useInvalidate() {
  const client = useQueryClient()
  return (...keys: string[]) =>
    Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key] })))
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

// Everything new figures for existing rides can change (after the server's recompute).
export const RECOMPUTED_KEYS = [...NEW_RIDE_KEYS, 'compare', 'streams', 'map']
