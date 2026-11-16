import type { Locator, Page } from '@playwright/test'

// The header on every page: the app's name, the main navigation and the light/dark toggle
// (a sun and a moon; the same toggle is on the Settings page, so these are scoped to the
// header). Units are switched on the Settings page only.
export class Header {
  readonly root: Locator
  readonly nav: Locator
  readonly libraryLink: Locator
  readonly importLink: Locator
  readonly bikesLink: Locator
  readonly settingsLink: Locator
  readonly theme: Locator
  // Pressed (aria-pressed) when it's the mode in use; each shows its name as a hover hint.
  readonly lightMode: Locator
  readonly darkMode: Locator

  constructor(page: Page) {
    this.root = page.getByRole('banner')
    this.nav = page.getByRole('navigation', { name: 'Main' })
    this.libraryLink = this.nav.getByRole('link', { name: 'Library', exact: true })
    this.importLink = this.nav.getByRole('link', { name: 'Import', exact: true })
    this.bikesLink = this.nav.getByRole('link', { name: 'Bikes', exact: true })
    this.settingsLink = this.nav.getByRole('link', { name: 'Settings', exact: true })
    this.theme = this.root.getByRole('group', { name: 'Theme' })
    this.lightMode = this.theme.getByRole('button', { name: 'Light mode' })
    this.darkMode = this.theme.getByRole('button', { name: 'Dark mode' })
  }

  // The hint shown on hover or keyboard focus, e.g. hint(header.darkMode) → "Dark mode".
  hint(button: Locator): Locator {
    return button.getByText(/mode$/)
  }
}
