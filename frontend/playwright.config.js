import { defineConfig } from "@playwright/test";
export default defineConfig({
  globalSetup: './tests/global-setup.js',
  testDir: "./tests",
  testIgnore: "reference-reuse.spec.js",
  workers: 1,
  timeout: 120000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1100 },
    screenshot: "only-on-failure",
    storageState: "../runs/playwright-storage.json",
  },
  webServer: [
    {
      command:
        ".venv\\Scripts\\python.exe -m uvicorn pcb_landmarks.web:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 60000,
      env: {
        PCB_ADMIN_USERNAME: "admin",
        PCB_ADMIN_PASSWORD: "playwright-test-password",
        PCB_WEB_STORAGE: "runs/playwright-auth-v5",
      },
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
    },
  ],
});
