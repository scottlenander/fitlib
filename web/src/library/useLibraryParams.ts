// The library's search, filters, sort and page, kept in the URL so a link or reload shows
// the same rides.
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'
import type { SortKey } from '../api/rides'
import { fromParams, toParams, type LibraryState } from './libraryQuery'

export function useLibraryParams() {
  const [params, setParams] = useSearchParams()
  const state = fromParams(params)

  // The URL state as last set, which may be ahead of this render: two quick changes (such
  // as "Clear filters" then a new filter) must build on each other, not on the same render.
  const latest = useRef(params)
  useEffect(() => {
    latest.current = params
  }, [params])

  // Changing a filter or sort starts again from page 1, unless paging itself.
  function update(changes: Partial<LibraryState>, keepPage = false) {
    const next = toParams({
      ...fromParams(latest.current),
      ...changes,
      ...(keepPage ? {} : { page: 1 }),
    })
    latest.current = next
    setParams(next)
  }

  // A new column starts newest/largest first; the same column flips.
  function sortBy(key: SortKey) {
    update({ sort: key, asc: state.sort === key ? !state.asc : false })
  }

  return { state, update, sortBy }
}
