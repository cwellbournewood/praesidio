import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Playwright runs against static HTML fixtures we ship under `e2e/fixtures/`.
 * We do NOT hit the real chatgpt.com / claude.ai sites in CI — those would
 * be flaky, copyrighted, and rate-limited. The fixtures replicate the
 * minimal DOM shape (textarea + send button + response container) so the
 * intercept + restore path is exercised end-to-end.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: `file://${resolve(__dirname, 'e2e/fixtures').replace(/\\/g, '/')}/`,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
