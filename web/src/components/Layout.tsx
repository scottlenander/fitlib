import { NavLink, Outlet } from 'react-router'
import { DisplaySwitches } from './DisplaySwitches'

// Header with the app's name, the main navigation and the display switches, around each page.
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
          <NavLink to="/bikes">Bikes</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="header-switches">
          <DisplaySwitches />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
