// The trends page's range, period and choices, kept in the URL.
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { fromParams, toParams, type TrendsState } from './trendsQuery'

export function useTrendsParams() {
  const [params, setParams] = useSearchParams()
  const search = params.toString()
  // The choice just made: the URL updates in a transition, and the controls should follow
  // at once. It only counts until the URL changes (to it, or by going back).
  const [changed, setChanged] = useState<{ from: string; to: TrendsState }>()
  const state = changed?.from === search ? changed.to : fromParams(params)

  function update(changes: Partial<TrendsState>) {
    const next = { ...state, ...changes }
    setChanged({ from: search, to: next })
    setParams(toParams(next))
  }

  return { state, update }
}
