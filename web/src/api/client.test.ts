import { describe, expect, it } from 'vitest'
import { ApiError, missingRides, shouldRetry } from './client'

describe('shouldRetry', () => {
  it('never retries an answer saying the request was wrong (4xx)', () => {
    expect(shouldRetry(0, new ApiError(404, 'No ride matches'))).toBe(false)
    expect(shouldRetry(0, new ApiError(422, 'Bad smoothing'))).toBe(false)
  })

  it('retries server and network trouble up to three times', () => {
    expect(shouldRetry(0, new ApiError(503, 'Unavailable'))).toBe(true)
    expect(shouldRetry(2, new TypeError('Failed to fetch'))).toBe(true)
    expect(shouldRetry(3, new TypeError('Failed to fetch'))).toBe(false)
  })
})

describe('missingRides', () => {
  it('reads the rides an error says are gone', () => {
    expect(missingRides(new ApiError(404, '2 rides are gone', ['a', 'b']))).toEqual(['a', 'b'])
  })

  it('is empty for other errors, or none', () => {
    expect(missingRides(new ApiError(404, 'No ride matches'))).toEqual([])
    expect(missingRides(new Error('boom'))).toEqual([])
    expect(missingRides(null)).toEqual([])
  })
})
