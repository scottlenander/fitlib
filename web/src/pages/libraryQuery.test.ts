// The library's URL state: reading it, writing it back and turning it into an API query.
import { describe, expect, test } from 'vitest'
import { DEFAULT_LIMIT, fromParams, hasFilters, toParams, toQuery } from './libraryQuery'

const parse = (search: string) => fromParams(new URLSearchParams(search))

describe('reading the URL', () => {
  test('an empty URL means newest first, page 1, default page size, no filters', () => {
    const state = parse('')

    expect(state).toMatchObject({ sort: 'start', asc: false, page: 1, limit: DEFAULT_LIMIT })
    expect(hasFilters(state)).toBe(false)
  })

  test('unknown or out-of-range values fall back to defaults', () => {
    const state = parse('source=strava&where=moon&sort=speed&page=-2&limit=500')

    expect(state).toMatchObject({ source: '', where: '', sort: 'start', page: 1, limit: 200 })
  })
})

describe('writing the URL', () => {
  test('only values that differ from the defaults are kept', () => {
    const params = toParams(parse('q=%20cobbles%20&sort=start&dir=desc&page=1&limit=25'))

    expect(params.toString()).toBe('q=cobbles')
  })

  test('a full state round-trips', () => {
    const search =
      'q=x&source=garmin&where=outdoor&since=2025-08-01&until=2025-08-31&power=yes&min=30&sort=power&dir=asc&page=2&limit=10'

    expect(toParams(parse(search)).toString()).toBe(search)
  })
})

describe('the API query', () => {
  test('filters become API parameters; "to" includes the whole day', () => {
    const query = toQuery(
      parse('source=zwift&where=indoor&since=2025-08-01&until=2025-08-31&power=no&min=45'),
    )

    expect(query).toMatchObject({
      source: 'zwift',
      indoor: true,
      since: '2025-08-01',
      until: '2025-09-01',
      has_power: false,
      min_duration_s: 2700,
    })
  })

  test('the page and size become an offset and limit', () => {
    expect(toQuery(parse('page=3&limit=10'))).toMatchObject({ offset: 20, limit: 10 })
  })

  test('sorting ascending turns off descending', () => {
    expect(toQuery(parse('sort=distance&dir=asc'))).toMatchObject({ sort: 'distance', desc: false })
  })
})
