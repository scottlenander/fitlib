import { expect, type Page } from '@playwright/test'
import { AxeBuilder } from '@axe-core/playwright'

// Automated WCAG 2.2 AA checks (axe-core). These catch about a third of accessibility
// problems, such as missing labels, low contrast and broken ARIA. Keyboard and screen
// reader checks still need a person.
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

// Scans the page as it is now. On failure, lists each problem and where it is.
export async function expectNoViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
  const summary = violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} at ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
  expect(summary, `accessibility problems on ${page.url()}`).toEqual([])
}
