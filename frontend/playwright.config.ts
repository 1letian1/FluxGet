import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  globalTeardown: './global-teardown.ts',
  fullyParallel: false,
  reporter: 'list',
  outputDir: '../test-results/playwright',
  use: {
    baseURL: 'http://127.0.0.1:8766',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: '.venv\\Scripts\\python.exe -m tests.e2e.server',
      cwd: '..',
      url: 'http://127.0.0.1:8766/api/v1/health',
      reuseExistingServer: false,
      gracefulShutdown: { signal: 'SIGINT', timeout: 1_000 },
      timeout: 30_000,
    },
  ],
})
