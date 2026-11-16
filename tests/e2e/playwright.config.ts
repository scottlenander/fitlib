import { defineConfig, devices } from '@playwright/test'

// scripts/e2e-server imports the fixture rides into a fresh temp library and serves the
// app here in e2e mode.
const PORT = Number(process.env.E2E_PORT ?? 3200)
const BASE_URL = `http://localhost:${PORT}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  // In CI, also annotate failures on the GitHub run; the HTML report is uploaded as a file.
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'html',
  use: {
    baseURL: BASE_URL,
    // Kept only for failed tests, so a failure can be replayed in the report.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  // Builds web/ if needed, imports the fixtures and serves them; stopped afterwards.
  webServer: {
    command: '../../scripts/e2e-server',
    env: { PORT: String(PORT) },
    url: `${BASE_URL}/api/health`,
    // Locally, reuse a server you already started with scripts/e2e-server (no re-import).
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
