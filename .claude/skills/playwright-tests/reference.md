# Templates and recipes

Copy these shapes. Imports use relative paths from the spec (`'../../pageObjects/...'`). Prettier settings are in `tests/e2e/.prettierrc.json`: no semicolons, single quotes, 100-character lines.

## Spec

```ts
import { test, expect } from '@playwright/test'
import { RidePage } from '../../pageObjects/ridePage'
import { RIDES } from '../../libs/constants'
import { TestData } from '../../libs/testData'

// Read-only: opened to check its figures.
const RIDE = RIDES.INTERVALS

test('a ride with power shows its training figures', async ({ page, request }) => {
  const ride = new RidePage(page)

  await test.step('Open the interval ride', async () => {
    await ride.goto(await new TestData(request).rideId(RIDE.file))
    await expect(ride.heading).toHaveText(RIDE.name)
  })

  await test.step('Training, with an estimated FTP', async () => {
    await expect(ride.training.value('FTP')).toHaveText('217 W (estimated)')
    await expect(ride.training.value('TSS')).toHaveText('113')
  })
})
```

A test that changes a ride claims it in `libs/constants.ts` and resets it first:

```ts
// Renamed and tagged; claimed in libs/constants.ts.
const RIDE = RIDES.SOME_RIDE

test('...', async ({ page, request }) => {
  const testData = new TestData(request)
  let rideId = ''

  await test.step('Start with no edits', async () => {
    rideId = await testData.rideId(RIDE.file)
    await testData.resetMeta(rideId)
  })
  // ...
})
```

## Page object

```ts
import type { Locator, Page } from '@playwright/test'
import { Header } from './components/header'

// Settings (/settings): the athlete history and bikes.
export class SettingsPage {
  readonly page: Page
  readonly header: Header
  readonly heading: Locator
  readonly history: Locator

  constructor(page: Page) {
    this.page = page
    this.header = new Header(page)
    this.heading = page.getByRole('heading', { name: 'Settings', level: 1 })
    this.history = page.getByRole('table', { name: 'Athlete history' })
  }

  async goto() {
    await this.page.goto('/settings')
  }

  // One history row, found by its date.
  entry(date: string): Locator {
    return this.history
      .getByRole('row')
      .filter({ has: this.page.getByRole('rowheader', { name: date }) })
  }
}
```

- File `pageObjects/settingsPage.ts`, class `SettingsPage`.
- If the page is reached from the header, add the nav link to `Header` (scoped to the `Main` navigation, `exact: true`).

## Component

A part of a page with its own root, exposed as a field of the page:

```ts
import type { Locator, Page } from '@playwright/test'

// A group of labelled figures shown as cards, on the ride page.
export class Stats {
  readonly page: Page
  readonly root: Locator

  constructor(page: Page, testId: string) {
    this.page = page
    this.root = page.getByTestId(testId)
  }

  value(label: string): Locator {
    return this.root
      .getByTestId('stat')
      .filter({ has: this.page.getByRole('term').filter({ hasText: new RegExp(`^${label}$`) }) })
      .getByRole('definition')
  }
}
```

## Adding a test id to a component

```tsx
<tr data-testid="ride-row">...</tr>
<p data-testid="ride-count" aria-live="polite">...</p>
```

Keep the existing classes; the id is added beside them. Ids stay in production.

## Adding a TestData shortcut

1. Add a route to `make_router` in `src/fitlib/api/routers/e2e.py`, with an API test in `tests/api/test_e2e.py` (including the "absent outside e2e mode" case).
2. Add a method to `TestData` in `libs/testData.ts`.
3. Make sure some test makes the same change through the UI, and add it to the shortcut list in the README.

## Adding a page to the accessibility scan

In `tests/accessibility/pages.spec.ts`, add a step to the test (it runs in light and dark mode):

```ts
await test.step('Settings', async () => {
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expectNoViolations(page)
})
```
