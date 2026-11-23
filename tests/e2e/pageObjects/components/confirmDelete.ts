import type { Locator, Page } from '@playwright/test'

// The dialog that asks before deleting rides, from a ride's page or the library's
// selection. Cancel has the focus when it opens.
export class ConfirmDelete {
  readonly root: Locator
  // "Delete this ride?" or "Delete 3 rides?"
  readonly heading: Locator
  // The rides' names (the first five, then "and n more").
  readonly rides: Locator
  readonly cancel: Locator
  // "Delete 1 ride" / "Delete 3 rides".
  readonly confirm: Locator
  readonly error: Locator

  constructor(page: Page) {
    this.root = page.getByRole('dialog', { name: /^Delete / })
    this.heading = this.root.getByRole('heading', { level: 2 })
    this.rides = this.root.getByTestId('confirm-delete-rides').getByRole('listitem')
    this.cancel = this.root.getByRole('button', { name: 'Cancel' })
    this.confirm = this.root.getByRole('button', { name: /^Delete \d+ rides?$/ })
    this.error = this.root.getByTestId('form-error')
  }
}
