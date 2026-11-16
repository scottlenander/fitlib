import type { Locator, Page } from '@playwright/test'

// The header on every page: the app's name, the main navigation and the display switches
// (the same switches are on the Settings page, so these are scoped to the header).
export class Header {
  readonly root: Locator
  readonly nav: Locator
  readonly libraryLink: Locator
  readonly importLink: Locator
  readonly bikesLink: Locator
  readonly settingsLink: Locator
  readonly darkMode: Locator
  readonly metricUnits: Locator

  constructor(page: Page) {
    this.root = page.getByRole('banner')
    this.nav = page.getByRole('navigation', { name: 'Main' })
    this.libraryLink = this.nav.getByRole('link', { name: 'Library', exact: true })
    this.importLink = this.nav.getByRole('link', { name: 'Import', exact: true })
    this.bikesLink = this.nav.getByRole('link', { name: 'Bikes', exact: true })
    this.settingsLink = this.nav.getByRole('link', { name: 'Settings', exact: true })
    this.darkMode = this.root.getByRole('switch', { name: 'Dark mode' })
    this.metricUnits = this.root.getByRole('switch', { name: 'Metric units' })
  }
}
