import {defineConfig} from '@playwright/test';

process.env.PANEL_E2E_PRODUCTION = '1';
export default defineConfig({
  testDir: './e2e', testMatch: '**/*.measurement.ts',
  globalSetup: './e2e/setup.ts', workers: 1, fullyParallel: false, retries: 0,
  timeout: 600_000, expect: {timeout: 20_000},
  outputDir: './test-results/mvp-performance',
  reporter: [['list'], ['json', {outputFile: process.env.PANEL_MVP_OPEN_ONLY === '1'
    ? '/tmp/panelflow-p3-t14-cached-open.json' : '/tmp/panelflow-p3-t14-performance.json'}]],
  use: {browserName: 'chromium', headless: false,
    viewport: {width: 1440, height: 1000},
    trace: 'retain-on-failure', screenshot: 'only-on-failure'},
});
