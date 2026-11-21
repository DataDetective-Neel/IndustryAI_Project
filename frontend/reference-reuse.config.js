import { defineConfig } from '@playwright/test';
export default defineConfig({
  outputDir: '../runs/reference-reuse/playwright',
  testDir: './tests', testMatch: 'reference-reuse.spec.js', workers: 1, timeout: 120000,
  use: { baseURL: 'http://127.0.0.1:8001', viewport: {width:1440, height:1100}, screenshot:'only-on-failure' },
  webServer: {
    command: '.venv\\Scripts\\python.exe -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8001',
    cwd: '..', env: {PCB_CHECKPOINT:'runs/reference-reuse/absent.pt'},
    url:'http://127.0.0.1:8001/api/health', reuseExistingServer:false, timeout:60000,
  },
});
