import type { Locator, Page } from '@playwright/test'

// The header on every page: the app's name, the main navigation and the units switch.
export class Header {
  readonly nav: Locator
  readonly libraryLink: Locator
  readonly importLink: Locator
  readonly units: Locator
  readonly imperial: Locator
  readonly metric: Locator

  constructor(page: Page) {
    this.nav = page.getByRole('navigation', { name: 'Main' })
    this.libraryLink = this.nav.getByRole('link', { name: 'Library', exact: true })
    this.importLink = this.nav.getByRole('link', { name: 'Import', exact: true })
    this.units = page.getByRole('group', { name: 'Units' })
    this.imperial = this.units.getByRole('radio', { name: 'Imperial' })
    this.metric = this.units.getByRole('radio', { name: 'Metric' })
  }
}
