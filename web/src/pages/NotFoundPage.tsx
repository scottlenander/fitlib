import { Link } from 'react-router'
import { usePageTitle } from '../usePageTitle'

export function NotFoundPage() {
  usePageTitle('Page not found')
  return (
    <>
      <h1>Page not found</h1>
      <p>
        There's nothing at this address. <Link to="/">Back to the library</Link>
      </p>
    </>
  )
}
