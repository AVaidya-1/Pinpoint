import path from 'path';
import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

export default defineConfig({
  testDir: path.join(root, 'frontend', 'tests'),
  testMatch: '**/e2e.spec.ts',
  timeout: 120000,
  expect: { timeout: 30000 },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    screenshot: 'off',
    trace: 'off',
  },
  outputDir: path.join(root, 'out', 'orchestration', 'import-viewer', 'test-output'),
  reporter: [['list']],
});
