import { request } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

export default async function globalSetup(config) {
  const baseURL = new URL(config.projects[0].use.baseURL).origin;
  const context = await request.newContext({ baseURL });
  const response = await context.post('/api/auth/login', { data: {
    username: 'admin', password: 'playwright-test-password',
  }});
  if (!response.ok()) throw new Error(`Playwright login failed: ${response.status()} ${await response.text()}`);
  const { token } = await response.json();
  const storage = { cookies: [], origins: [...new Set([baseURL, 'http://127.0.0.1:8000', 'http://127.0.0.1:5173'])].map(origin => ({
    origin,
    localStorage: [{ name: 'aoi_token', value: token }],
  })) };
  const output = path.resolve(config.projects[0].use.storageState);
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(storage));
  await context.dispose();
}
