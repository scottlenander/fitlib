import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { test, expect, type Page } from '@playwright/test'
import { LibraryPage } from '../../pageObjects/libraryPage'
import { RidePage } from '../../pageObjects/ridePage'
import { TrendsPage } from '../../pageObjects/trendsPage'
import { SettingsPage } from '../../pageObjects/settingsPage'
import { BikesPage } from '../../pageObjects/bikesPage'
import { TestData } from '../../libs/testData'
import { RIDES } from '../../libs/constants'

// Read-only: the interval ride's page is opened to draw its charts under the policy.
const RIDE = RIDES.INTERVALS
// Another site's page, served by the test on another local port. A public site would do the
// same, but Chromium already stops public sites reaching localhost ("Local Network Access");
// not every browser does, so fitlib's own check is tested with a page Chromium lets through.
async function otherSite(): Promise<{ url: string; close: () => void }> {
  const server = http.createServer((_, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html' })
    response.end('<!doctype html><title>Other site</title>')
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const { port } = server.address() as AddressInfo
  return { url: `http://127.0.0.1:${port}/`, close: () => server.close() }
}

// Collects the browser's Content-Security-Policy complaints (Chromium logs each one).
function cspViolations(page: Page): string[] {
  const found: string[] = []
  page.on('console', (message) => {
    if (message.text().includes('Content Security Policy')) found.push(message.text())
  })
  return found
}

test('every page works under the content security policy', async ({ page, request }) => {
  const library = new LibraryPage(page)
  const ride = new RidePage(page)
  const trends = new TrendsPage(page)
  const settings = new SettingsPage(page)
  const bikes = new BikesPage(page)
  const violations = cspViolations(page)
  const rideId = await new TestData(request).rideId(RIDE.file)

  await test.step('The app is served with the policy', async () => {
    const response = await page.goto('/')
    expect(response?.headers()['content-security-policy']).toContain("script-src 'self'")
    await expect(library.heading).toBeVisible()
  })

  await test.step('Open a ride with its charts', async () => {
    await ride.goto(rideId)
    await expect(ride.heading).toHaveText(RIDE.name)
    await expect(ride.traceChart).toBeVisible()
  })

  await test.step('Open Trends, Bikes and Settings', async () => {
    await trends.goto()
    await expect(trends.heading).toBeVisible()
    await bikes.goto()
    await expect(bikes.heading).toBeVisible()
    await settings.goto()
    await expect(settings.heading).toBeVisible()
  })

  await test.step('A theme chosen in the app applies before the app itself runs', async () => {
    await settings.header.theme.click()
    const chosen = await page.evaluate(() => localStorage.getItem('fitlib.theme'))
    // Without the app's code, only the theme script (no longer inline) can set it.
    await page.route('**/assets/index-*.js', (route) => route.abort())
    await page.reload()
    await expect(page.locator('html'), {
      message: 'The theme script should set the remembered theme on its own',
    }).toHaveAttribute('data-theme', chosen ?? 'missing')
    await page.unroute('**/assets/index-*.js')
  })

  await test.step('Nothing was blocked', () => {
    expect(violations, { message: 'No page should break the policy' }).toEqual([])
  })
})

test('a page on another site cannot import into the library', async ({ page, baseURL }) => {
  const site = await otherSite()
  // The status fitlib sent, read from the browser's own network log: the page itself is
  // never allowed to see it.
  const statuses: number[] = []
  const urls = new Map<string, string>()
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.enable')
  cdp.on('Network.requestWillBeSent', (e) => urls.set(e.requestId, e.request.url))
  cdp.on('Network.responseReceivedExtraInfo', (e) => {
    if (urls.get(e.requestId)?.endsWith('/api/imports')) statuses.push(e.statusCode)
  })

  await test.step('Open a page on another site that uploads a file to fitlib', async () => {
    await page.goto(site.url)
    // A cross-site form upload: browsers send it without asking the server first. The
    // bytes are harmless even if accepted (an import that fails).
    const outcome = await page.evaluate(async (url) => {
      const form = new FormData()
      form.append('files', new Blob(['not a ride']), 'ride.fit')
      try {
        await fetch(url, { method: 'POST', mode: 'no-cors', body: form })
        return 'answered'
      } catch {
        return 'failed'
      }
    }, `${baseURL}/api/imports`)
    site.close()
    expect(outcome, {
      message: "fitlib's answer should be kept from the other site's page",
    }).toBe('failed')
  })

  await test.step('fitlib refused it', async () => {
    await expect.poll(() => statuses, { message: 'fitlib should answer 403' }).toEqual([403])
  })
})
