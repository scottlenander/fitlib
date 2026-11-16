import type { Locator, Page } from '@playwright/test'

// A group of labelled figures shown as cards ("Distance 19.9 mi"), on the ride page.
export class Stats {
  readonly page: Page
  readonly root: Locator
  readonly labels: Locator

  constructor(page: Page, testId: string) {
    this.page = page
    this.root = page.getByTestId(testId)
    this.labels = this.root.getByRole('term')
  }

  // The value shown for a label, e.g. value('Distance') → "19.9 mi".
  value(label: string): Locator {
    return this.root
      .getByTestId('stat')
      .filter({ has: this.page.getByRole('term').filter({ hasText: new RegExp(`^${label}$`) }) })
      .getByRole('definition')
  }
}
