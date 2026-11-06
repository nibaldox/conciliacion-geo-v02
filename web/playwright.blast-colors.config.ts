import { defineConfig } from '@playwright/test';

const executablePath = process.env.BLAST_COLORS_CHROME_PATH || undefined;

export default defineConfig({
  testDir: './e2e',
  testMatch: /blast-colors\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5173',
    launchOptions: {
      executablePath,
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
    },
  },
  projects: [{ name: 'chromium-gpu', use: { browserName: 'chromium' } }],
});
