import { NavLink, Outlet } from 'react-router'
import { NewRidesNotice } from './NewRidesNotice'
import { useRecomputeRefresh } from './useRecomputeRefresh'
import { ThemeToggle } from '../shared/ThemeToggle'

// Header with the app's name, the main navigation and the light/dark toggle, around each page.
export function Layout() {
  useRecomputeRefresh()
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <NavLink to="/" className="brand">
          fitlib
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Library
          </NavLink>
          <NavLink to="/trends">Trends</NavLink>
          <NavLink to="/import">Import</NavLink>
          <NavLink to="/bikes">Bikes</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="header-switches">
          <ThemeToggle />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <NewRidesNotice />
        <Outlet />
      </main>
    </>
  )
}
