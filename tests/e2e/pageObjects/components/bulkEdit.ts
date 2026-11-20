import type { Locator, Page } from '@playwright/test'

// The library's "Edit n rides" form, under the selection bar: effort, bike and tags for
// every selected ride at once. Shown after the bar's Edit button is pressed.
export class BulkEdit {
  readonly root: Locator
  // "Edit 2 rides"
  readonly heading: Locator
  readonly effort: Locator
  readonly bike: Locator
  readonly addTags: Locator
  readonly removeTags: Locator
  // "Apply to 2 rides": disabled until something is to change.
  readonly apply: Locator
  readonly close: Locator
  // "Updated 2 rides."
  readonly notice: Locator
  readonly error: Locator

  constructor(page: Page) {
    this.root = page.getByRole('form', { name: /^Edit \d+ rides?$/ })
    this.heading = this.root.getByRole('heading', { level: 2 })
    this.effort = this.root.getByLabel('Effort')
    this.bike = this.root.getByLabel('Bike')
    this.addTags = this.root.getByLabel('Add tags')
    this.removeTags = this.root.getByLabel('Remove tags')
    this.apply = this.root.getByRole('button', { name: /^Apply to/ })
    this.close = this.root.getByRole('button', { name: 'Close' })
    this.notice = this.root.getByTestId('form-notice')
    this.error = this.root.getByTestId('form-error')
  }
}
