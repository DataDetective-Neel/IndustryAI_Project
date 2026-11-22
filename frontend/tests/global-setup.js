import { request } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

export default async function globalSetup() {
  const context = await request.newContext({ baseURL: 'http://127.0.0.1:8000' });
  const response = await context.post('/api/auth/login', { data: {
    username: 'admin', password: 'playwright-test-password',
  }});
  if (!response.ok()) throw new Error(`Playwright login failed: ${response.status()} ${await response.text()}`);
  const { token } = await response.json();
  const storage = { cookies: [], origins: [8000, 5173].map(port => ({
    origin: `http://127.0.0.1:${port}`,
    localStorage: [{ name: 'aoi_token', value: token }],
  })) };
  const output = path.resolve('..', 'runs', 'playwright-storage.json');
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(storage));
  await context.dispose();
}
