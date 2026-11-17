import type { Locator, Page } from '@playwright/test'

// The "Similar rides" section on the ride page: tabs for rides on the same route and rides
// with a similar effort. Each tab loads its list when first shown.
export class SimilarRides {
  readonly page: Page
  readonly root: Locator
  readonly routeTab: Locator
  readonly effortTab: Locator
  readonly routeTable: Locator
  readonly effortTable: Locator
  readonly rows: Locator
  // Why there's nothing to list: no GPS, nobody else on the route, nothing to compare.
  readonly empty: Locator

  constructor(page: Page) {
    this.page = page
    this.root = page.getByRole('region', { name: 'Similar rides' })
    this.routeTab = this.root.getByRole('tab', { name: 'Same route' })
    this.effortTab = this.root.getByRole('tab', { name: 'Similar efforts' })
    this.routeTable = this.root.getByRole('table', { name: 'Rides on the same route' })
    this.effortTable = this.root.getByRole('table', { name: 'Rides with a similar effort' })
    this.rows = this.root.getByTestId('similar-row')
    this.empty = this.root.getByTestId('similar-empty')
  }

  // A listed ride's row, by its name.
  row(name: string): Locator {
    return this.rows.filter({ has: this.page.getByRole('link', { name, exact: true }) })
  }

  // A listed ride's Compare link: opens this ride next to it.
  compareWith(name: string): Locator {
    return this.root.getByRole('link', { name: `Compare with ${name}`, exact: true })
  }

  // Above the same-route table: opens this ride with its closest matches (up to 3).
  compareClosest(count: number): Locator {
    return this.root.getByRole('link', { name: `Compare with the ${count} closest rides` })
  }

  rideLink(name: string): Locator {
    return this.root.getByRole('link', { name, exact: true })
  }
}
