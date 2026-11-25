// The compare page's address.
import { describe, expect, test } from 'vitest'
import { compareUrl, parseIds } from './compare'

describe('compare address', () => {
  test('ids are comma-separated in order', () => {
    expect(compareUrl(['a', 'b', 'c'])).toBe('/compare?ids=a,b,c')
  })

  test('blanks and repeats are dropped from the address', () => {
    expect(parseIds(' a, ,b,a,c ')).toEqual(['a', 'b', 'c'])
    expect(parseIds(null)).toEqual([])
  })
})
