import { defineConfig } from "@playwright/test";
// Each invocation owns fresh test data; existing application records remain untouched.
const storage = `runs/playwright-auth-${Date.now()}-${process.pid}`;
export default defineConfig({
  globalSetup: './tests/global-setup.js',
  testDir: "./tests",
  testIgnore: ["reference-reuse.spec.js", "repair-workflow.spec.js"],
  workers: 1,
  timeout: 120000,
  expect: {timeout: 30000},
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
      reuseExistingServer: false,
      timeout: 60000,
      env: {
        PCB_ADMIN_USERNAME: "admin",
        PCB_ADMIN_PASSWORD: "playwright-test-password",
        PCB_WEB_STORAGE: storage,
      },
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
    },
  ],
});
