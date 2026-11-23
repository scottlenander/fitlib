// Whether outdoor routes are drawn over OpenStreetMap's street map. Off unless chosen: the
// map images come from openstreetmap.org, which then sees the areas you look at. Remembered
// in this browser.
import { useState } from 'react'

const STORAGE_KEY = 'fitlib.streetMap'

export function rememberedStreetMap(read: () => string | null): boolean {
  try {
    return read() === 'on'
  } catch {
    return false // storage blocked: off
  }
}

export function useStreetMap(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => rememberedStreetMap(() => localStorage.getItem(STORAGE_KEY)))
  function set(value: boolean) {
    setOn(value)
    try {
      localStorage.setItem(STORAGE_KEY, value ? 'on' : 'off')
    } catch {
      // Storage blocked: the choice lasts until the page is left.
    }
  }
  return [on, set]
}
