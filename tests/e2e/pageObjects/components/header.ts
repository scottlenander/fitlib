import type { Locator, Page } from '@playwright/test'

// The header on every page: the app's name, the main navigation and the light/dark toggle.
// The toggle is one button showing the mode in use (a sun or a moon), named "Light mode" or
// "Dark mode"; clicking switches mode. The same toggle is on the Settings page, so this one
// is scoped to the header. Units are switched on the Settings page only.
// The theme button's name and hint: the mode in use.
export const THEME_NAME = /^(Light|Dark) mode$/

export class Header {
  readonly root: Locator
  readonly nav: Locator
  readonly libraryLink: Locator
  readonly trendsLink: Locator
  readonly importLink: Locator
  readonly bikesLink: Locator
  readonly settingsLink: Locator
  readonly theme: Locator
  // The theme button's hint, shown on hover or keyboard focus: "Light mode" or "Dark mode".
  readonly themeHint: Locator

  constructor(page: Page) {
    this.root = page.getByRole('banner')
    this.nav = page.getByRole('navigation', { name: 'Main' })
    this.libraryLink = this.nav.getByRole('link', { name: 'Library', exact: true })
    this.trendsLink = this.nav.getByRole('link', { name: 'Trends', exact: true })
    this.importLink = this.nav.getByRole('link', { name: 'Import', exact: true })
    this.bikesLink = this.nav.getByRole('link', { name: 'Bikes', exact: true })
    this.settingsLink = this.nav.getByRole('link', { name: 'Settings', exact: true })
    this.theme = this.root.getByRole('button', { name: THEME_NAME })
    this.themeHint = this.theme.getByText(THEME_NAME)
  }
}
