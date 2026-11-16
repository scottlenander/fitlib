import { NavLink, Outlet } from 'react-router'
import { UnitsToggle } from './UnitsToggle'

// Header with the app's name, the main navigation and the units switch, around each page.
export function Layout() {
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
          <NavLink to="/import">Import</NavLink>
        </nav>
        <UnitsToggle />
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
