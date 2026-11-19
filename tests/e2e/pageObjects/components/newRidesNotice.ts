import type { Locator, Page } from '@playwright/test'

// Above every page's content: "1 new ride imported from a watched folder." with a link to it
// (or to the library, for several) and Dismiss. Only shown for rides the server's watcher
// imported after the page was opened; the app checks every 15 s (5 s on Settings).
export class NewRidesNotice {
  readonly root: Locator
  readonly open: Locator
  readonly openLibrary: Locator
  readonly dismiss: Locator

  constructor(page: Page) {
    this.root = page.getByTestId('new-rides-notice')
    this.open = this.root.getByRole('link', { name: 'Open it' })
    this.openLibrary = this.root.getByRole('link', { name: 'Open the library' })
    this.dismiss = this.root.getByRole('button', { name: 'Dismiss' })
  }
}
