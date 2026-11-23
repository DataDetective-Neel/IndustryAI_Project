import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: 'repair-workflow.spec.js', workers: 1, timeout: 120000,
  outputDir: '../runs/repair-browser',
  use: { baseURL: 'http://127.0.0.1:8012', viewport: {width: 1440, height: 1100}, screenshot: 'only-on-failure' },
  webServer: {
    command: '.venv\\Scripts\\python.exe -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8012',
    cwd: '..', url: 'http://127.0.0.1:8012/api/health', reuseExistingServer: false,
    env: { PCB_WEB_STORAGE: 'runs/repair-browser-storage', PCB_ADMIN_USERNAME: 'repair', PCB_ADMIN_PASSWORD: 'repair-browser-test-password' },
  },
});
