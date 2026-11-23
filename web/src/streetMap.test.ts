import { describe, expect, it } from 'vitest'
import { rememberedStreetMap } from './streetMap'

describe('rememberedStreetMap', () => {
  it('is on only when chosen', () => {
    expect(rememberedStreetMap(() => 'on')).toBe(true)
    expect(rememberedStreetMap(() => 'off')).toBe(false)
    expect(rememberedStreetMap(() => null)).toBe(false)
    expect(rememberedStreetMap(() => 'yes')).toBe(false)
  })

  it('is off when storage is blocked', () => {
    expect(
      rememberedStreetMap(() => {
        throw new Error('blocked')
      }),
    ).toBe(false)
  })
})
