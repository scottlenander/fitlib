import type { Locator, Page } from '@playwright/test'
import { BulkEdit } from './components/bulkEdit'
import { ConfirmDelete } from './components/confirmDelete'
import { Header } from './components/header'

// The ride library (/): search, filters, the rides table and paging. Filters, sort and
// page live in the URL, so goto() can open any state directly.
export class LibraryPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly search: Locator
  readonly searchButton: Locator
  readonly filters: Locator
  readonly source: Locator
  readonly where: Locator
  readonly power: Locator
  readonly from: Locator
  readonly to: Locator
  readonly minMinutes: Locator
  readonly tag: Locator
  readonly bike: Locator
  readonly effortFrom: Locator
  readonly effortTo: Locator
  readonly world: Locator
  readonly clearFilters: Locator
  // "Showing 1–8 of 8 rides" or "No rides found."
  readonly count: Locator
  readonly table: Locator
  readonly rows: Locator
  readonly estimatedNote: Locator
  readonly pager: Locator
  readonly previous: Locator
  readonly next: Locator
  readonly perPage: Locator
  // Above the table: what's selected ("Selected: …", "12 rides selected. …" or how many
  // to tick).
  readonly selectionStatus: Locator
  // "Compare (n)": only enabled with 2 to 4 rides selected.
  readonly compareButton: Locator
  // "Edit 2 rides": opens the bulk edit form for the selected rides.
  readonly editButton: Locator
  // "Delete 2 rides": asks, then deletes the selected rides.
  readonly deleteButton: Locator
  readonly confirmDelete: ConfirmDelete
  // "Deleted Garmin 2025-08-08 18:00." (from its page) or "Deleted 2 rides."
  readonly deletedNotice: Locator
  readonly clearSelection: Locator
  // The header checkbox that selects every ride on the page.
  readonly selectPage: Locator
  readonly bulkEdit: BulkEdit

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Library', level: 1 })
    this.search = page.getByRole('searchbox', { name: 'Search' })
    this.searchButton = page.getByRole('button', { name: 'Search', exact: true })
    this.filters = page.getByRole('group', { name: 'Filters' })
    this.source = this.filters.getByLabel('Source')
    this.where = this.filters.getByLabel('Where')
    this.power = this.filters.getByLabel('Power')
    this.from = this.filters.getByLabel('From', { exact: true })
    this.to = this.filters.getByLabel('To', { exact: true })
    this.minMinutes = this.filters.getByLabel('At least (minutes)')
    this.tag = this.filters.getByLabel('Tag')
    this.bike = this.filters.getByLabel('Bike')
    this.effortFrom = this.filters.getByLabel('Effort from')
    this.effortTo = this.filters.getByLabel('Effort to')
    this.world = this.filters.getByLabel('World')
    this.clearFilters = this.filters.getByRole('button', { name: 'Clear filters' })
    this.count = page.getByTestId('ride-count')
    this.table = page.getByRole('table', { name: 'Rides' })
    this.rows = this.table.getByTestId('ride-row')
    this.estimatedNote = page.getByText('* TSS from an estimated FTP')
    this.pager = page.getByRole('navigation', { name: 'Pages' })
    this.previous = this.pager.getByRole('button', { name: 'Previous' })
    this.next = this.pager.getByRole('button', { name: 'Next' })
    this.perPage = this.pager.getByLabel('Rides per page')
    this.selectionStatus = page.getByTestId('selection-status')
    this.compareButton = page.getByRole('button', { name: /^Compare \(\d+\)$/ })
    this.editButton = page.getByRole('button', { name: /^Edit \d+ rides?$/ })
    this.deleteButton = page.getByRole('button', { name: /^Delete \d+ rides?$/ })
    this.confirmDelete = new ConfirmDelete(page)
    this.deletedNotice = page.getByTestId('deleted-notice')
    this.clearSelection = page.getByRole('button', { name: 'Clear selection' })
    this.selectPage = this.table.getByRole('checkbox', { name: 'Select all rides on this page' })
    this.bulkEdit = new BulkEdit(page)
  }

  // Opens the library, optionally with URL parameters: { since: '2025-08-10', limit: '2' }.
  async goto(params: Record<string, string> = {}) {
    const query = new URLSearchParams(params).toString()
    await this.page.goto(query ? `/?${query}` : '/')
  }

  async searchFor(text: string) {
    await this.search.fill(text)
    await this.searchButton.click()
  }

  // A table row, found by the ride's name.
  row(name: string): Locator {
    return this.rows.filter({ has: this.page.getByRole('link', { name, exact: true }) })
  }

  // The checkbox that selects a ride, to compare or edit.
  pick(name: string): Locator {
    return this.table.getByRole('checkbox', { name: `Select ${name}`, exact: true })
  }

  rideLink(name: string): Locator {
    return this.table.getByRole('link', { name, exact: true })
  }

  // The links of the rides shown, in order (for checking which rides and their order).
  rideNames(): Locator {
    return this.rows.getByRole('link')
  }

  // A sortable column's header button: Date, Time, Distance or Avg power.
  sortButton(column: string): Locator {
    return this.table.getByRole('button', { name: column, exact: true })
  }

  columnHeader(column: string): Locator {
    return this.table.getByRole('columnheader', { name: column, exact: true })
  }

  pageStatus(current: number, total: number): Locator {
    return this.pager.getByText(`Page ${current} of ${total}`)
  }
}
