import { useEffect } from 'react'

// Sets the browser tab's title for a page: "Library · fitlib".
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · fitlib` : 'fitlib'
  }, [title])
}
