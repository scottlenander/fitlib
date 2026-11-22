// The library's URL state: reading it, writing it back and turning it into an API query.
import { describe, expect, test } from 'vitest'
import {
  DEFAULT_LIMIT,
  fromParams,
  hasFilters,
  toParams,
  toQuery,
  withSource,
  withWorld,
} from './libraryQuery'

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
      'q=x&source=garmin&where=outdoor&since=2025-08-01&until=2025-08-31&power=yes&min=30&tag=z2&bike=b1&rpe_min=3&rpe_max=7&world=watopia&sort=power&dir=asc&page=2&limit=10'

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

  test('tag, bike and effort filters', () => {
    expect(toQuery(parse('tag=z2&bike=b1&rpe_min=3&rpe_max=7'))).toMatchObject({
      tag: ['z2'],
      bike_id: 'b1',
      min_rpe: 3,
      max_rpe: 7,
    })
    expect(toQuery(parse('bike=none'))).toMatchObject({ has_bike: false, bike_id: undefined })
  })

  test('a Zwift world', () => {
    expect(toQuery(parse('world=makuri-islands'))).toMatchObject({ world: 'makuri-islands' })
    expect(toQuery(parse(''))).toMatchObject({ world: undefined })
  })

  test('an effort outside 1-10 is ignored', () => {
    expect(parse('rpe_min=0&rpe_max=11')).toMatchObject({ minRpe: '', maxRpe: '' })
  })

  test('every filter counts as a filter', () => {
    for (const search of ['tag=z2', 'bike=none', 'rpe_min=3', 'min=10', 'world=watopia']) {
      expect(hasFilters(parse(search)), search).toBe(true)
    }
  })

  test('the page and size become an offset and limit', () => {
    expect(toQuery(parse('page=3&limit=10'))).toMatchObject({ offset: 20, limit: 10 })
  })

  test('sorting ascending turns off descending', () => {
    expect(toQuery(parse('sort=distance&dir=asc'))).toMatchObject({ sort: 'distance', desc: false })
  })
})

describe('worlds and sources', () => {
  test('choosing a world drops another source, but keeps Zwift', () => {
    expect(withWorld(parse('source=garmin'), 'watopia')).toEqual({ world: 'watopia', source: '' })
    expect(withWorld(parse('source=zwift'), 'watopia')).toEqual({ world: 'watopia' })
    expect(withWorld(parse('source=garmin'), '')).toEqual({ world: '' })
  })

  test('choosing another source drops the world; Zwift or any keeps it', () => {
    expect(withSource('garmin')).toEqual({ source: 'garmin', world: '' })
    expect(withSource('zwift')).toEqual({ source: 'zwift' })
    expect(withSource('')).toEqual({ source: '' })
  })
})
