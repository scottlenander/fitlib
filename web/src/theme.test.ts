// Which theme applies: the viewer's remembered choice, else the system's.
import { describe, expect, test } from 'vitest'
import { rememberedTheme, resolveTheme } from './theme'

describe('remembered choice', () => {
  test.each([
    ['dark', 'dark'],
    ['light', 'light'],
    [null, null],
    ['purple', null],
  ])('stored %s reads as %s', (stored, expected) => {
    expect(rememberedTheme(() => stored)).toBe(expected)
  })

  test('blocked storage reads as no choice', () => {
    expect(
      rememberedTheme(() => {
        throw new Error('blocked')
      }),
    ).toBeNull()
  })
})

describe('theme in effect', () => {
  test('without a choice, the system decides', () => {
    expect([resolveTheme(null, true), resolveTheme(null, false)]).toEqual(['dark', 'light'])
  })

  test('a choice wins over the system', () => {
    expect([resolveTheme('light', true), resolveTheme('dark', false)]).toEqual(['light', 'dark'])
  })
})
