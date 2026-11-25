import { expect, test } from 'vitest'
import { parseTags } from './tags'

test('tags are split on commas, trimmed, and empty ones dropped', () => {
  expect(parseTags(' Z2, cobbles ,, base ')).toEqual(['Z2', 'cobbles', 'base'])
})

test('the same tag in another case is kept once', () => {
  expect(parseTags('Tempo, tempo, TEMPO')).toEqual(['Tempo'])
})

test('an empty line means no tags', () => {
  expect(parseTags('   ')).toEqual([])
})
