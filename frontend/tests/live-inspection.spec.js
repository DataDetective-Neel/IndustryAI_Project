import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

test.afterEach(async ({ page }) => {
  const token = await page.evaluate(() => localStorage.getItem('aoi_token')).catch(() => null);
  if (token) await page.request.delete('http://127.0.0.1:8000/api/golden-config', {
    headers: { Authorization: `Bearer ${token}` },
  });
});

test('imports multiple images and runs them through live inspection', async ({ page }) => {
  await page.goto('/#live');
  const token = await page.evaluate(() => localStorage.getItem('aoi_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const root = path.resolve('..');
  const referenceBytes = await fs.readFile(path.join(root, 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  const upload = await page.request.post('http://127.0.0.1:8000/api/photos', { multipart: {
    image: { name: 'ECCC5.jpg', mimeType: 'image/jpeg', buffer: referenceBytes },
  }});
  expect(upload.ok()).toBeTruthy();
  const reference = await upload.json();
  const labels = (await fs.readFile(path.join(root, 'PCB_Dataset_Pilot/labels/val/ECCC5.txt'), 'utf8')).trim().split(/\s+/).map(Number);
  const points = Array.from({length:4}, (_, i) => [labels[5+i*3]*reference.width, labels[6+i*3]*reference.height]);
  const confirmed = await page.request.post(`http://127.0.0.1:8000/api/references/${reference.id}`, {
    data: { points, board_polygon: [[221,115], [1002,115], [1002,1412], [221,1412]] },
  });
  expect(confirmed.ok()).toBeTruthy();
  const regions = JSON.parse(await fs.readFile(path.join(root, 'configs/components-ECCC5.json'), 'utf8'));
  const saved = await page.request.post('http://127.0.0.1:8000/api/golden-config', { headers, data: {
    reference_id: reference.id, components: regions.components, mode: 'automatic', sharpen: false,
  }});
  expect(saved.ok()).toBeTruthy();

  await page.getByLabel('Import inspection images').setInputFiles([
    path.join(root, 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'),
    path.join(root, 'PCB_Dataset_Pilot/images/val/ECCB5.jpg'),
  ]);
  await expect(page.getByText('2 images ready in imported dataset.')).toBeVisible();
  await page.getByLabel(/Inspection interval/).fill('0.5');
  await page.getByRole('button', { name: 'Start simulation' }).click();
  await expect(page.locator('.line-state')).toHaveText('running');
  await page.getByRole('button', { name: 'Pause' }).click();
  await expect(page.locator('.line-state')).toHaveText('paused');
  await page.getByRole('button', { name: 'Resume' }).click();
  await expect(page.locator('.line-state')).toHaveText('running');
  await page.getByRole('button', { name: 'Stop' }).click();
  await expect(page.locator('.line-state')).toHaveText('stopped', { timeout: 120000 });
  await page.getByRole('button', { name: 'Start simulation' }).click();
  await expect(page.locator('.line-state')).toHaveText('completed', { timeout: 120000 });
  await expect(page.locator('.live-counters article').filter({ hasText: 'Processed' })).toContainText('2');
  await expect.poll(() => page.locator('.history-panel tbody tr').count()).toBeGreaterThanOrEqual(2);
});

test('chunks sixteen selected images into one live queue', async ({ page }) => {
  await page.goto('/#live');
  const buffer = await fs.readFile(path.resolve('..', 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  await page.getByLabel('Import inspection images').setInputFiles(
    Array.from({ length: 16 }, (_, index) => ({
      name: `selected-${String(index).padStart(2, '0')}.jpg`,
      mimeType: 'image/jpeg',
      buffer,
    })),
  );
  await expect(page.getByText(/16 accepted, 0 skipped/i)).toBeVisible({ timeout: 30000 });
});
