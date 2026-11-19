import type { Locator, Page } from '@playwright/test'

// "Progress on this route" on the ride page: a chart of every ride on the route (average
// speed by default) and their table, folded under "Show table". Only there when at least one
// other ride shares the route.
export class RouteProgress {
  readonly page: Page
  readonly root: Locator
  readonly metric: Locator
  readonly chart: Locator
  readonly showTable: Locator
  readonly table: Locator
  readonly rows: Locator

  constructor(page: Page) {
    this.page = page
    this.root = page.getByRole('region', { name: 'Progress on this route' })
    this.metric = this.root.getByRole('combobox', { name: /^Show/ })
    this.chart = this.root.getByTestId('progress-chart')
    this.showTable = this.root.getByText('Show table')
    this.table = this.root.getByRole('table', { name: 'Rides on this route, oldest first' })
    this.rows = this.root.getByTestId('progress-row')
  }

  // Another ride's row, by the link to it.
  row(name: string): Locator {
    return this.rows.filter({ has: this.page.getByRole('link', { name, exact: true }) })
  }

  // The ride page's own ride, marked "(this ride)" rather than linked.
  thisRide(): Locator {
    return this.rows.filter({ hasText: '(this ride)' })
  }
}
