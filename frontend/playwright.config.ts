import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  globalSetup: './e2e/setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 45_000,
  expect: {timeout: 10_000},
  outputDir: './test-results',
  reporter: [['list'], ['html', {open: 'never'}]],
  use: {
    browserName: 'chromium',
    viewport: {width: 1440, height: 1000},
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Headless CI still uses an actual WebGL implementation and browser events.
    launchOptions: {args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']},
  },
});
