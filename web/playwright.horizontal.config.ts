import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  reporter: 'list',
  outputDir: '../data/local-review-logs/playwright-hdev',
  use: {
    baseURL: 'http://127.0.0.1:5174/conciliacion-geo-v02/',
    trace: 'off',
    ...devices['Desktop Chrome'],
    channel: 'msedge',
  },
  projects: [{ name: 'edge', use: { ...devices['Desktop Chrome'], channel: 'msedge' } }],
});
