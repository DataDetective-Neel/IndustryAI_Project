import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { confirmReference } from './reference-setup.js';

const root = path.resolve('..');

test.afterEach(async ({ page }) => {
  const token = await page.evaluate(() => localStorage.getItem('aoi_token')).catch(() => null);
  if (token) await page.request.delete('http://127.0.0.1:8000/api/golden-config', {
    headers: { Authorization: `Bearer ${token}` },
  });
});

test('golden proposals through live decisions update dashboard counts', async ({ page }) => {
  await page.goto('/#lab');
  const token = await page.evaluate(() => localStorage.getItem('aoi_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const before = await (await page.request.get('http://127.0.0.1:8000/api/dashboard', { headers })).json();

  const golden = path.join(root, 'PCB_Dataset_Pilot/images/val/ECCC5.jpg');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(golden);
  await expect(page.locator('rect.region-box').first()).toBeVisible();
  await page.getByRole('button', { name: 'Accept all proposals', exact: true }).click();

  const labels = (await fs.readFile(path.join(root, 'PCB_Dataset_Pilot/labels/val/ECCC5.txt'), 'utf8'))
    .trim().split(/\s+/).map(Number);
  const pointNames = ['upper_left_mount', 'upper_right_mount', 'lower_right_mount', 'lower_left_mount'];
  for (let index = 0; index < 4; index += 1) {
    await page.getByLabel(`${pointNames[index]} x`, { exact: true }).fill(String(labels[5 + index * 3] * 1174));
    await page.getByLabel(`${pointNames[index]} y`, { exact: true }).fill(String(labels[6 + index * 3] * 1536));
  }
  await confirmReference(page, [[221, 115], [1002, 115], [1002, 1412], [221, 1412]]);
  await page.getByRole('button', { name: 'Save for live line', exact: true }).click();
  await expect(page.getByText('Golden configuration saved for Live Inspection.')).toBeVisible();

  await page.getByRole('button', { name: 'Live Inspection' }).click();
  const inspection = await fs.readFile(path.join(root, 'PCB_Dataset_Pilot/images/val/ECCB5.jpg'));
  await page.getByLabel('Import inspection images').setInputFiles([
    { name: 'walkthrough-confirm.jpg', mimeType: 'image/jpeg', buffer: inspection },
    { name: 'walkthrough-dismiss.jpg', mimeType: 'image/jpeg', buffer: inspection },
  ]);
  await expect(page.getByText(/2 accepted, 0 skipped/i)).toBeVisible();
  await page.getByLabel(/Inspection interval/).fill('0.5');
  await page.getByRole('button', { name: 'Start simulation' }).click();
  await expect(page.locator('.line-state')).toHaveText('completed', { timeout: 120000 });

  const confirmed = page.locator('.review-grid > article').filter({ hasText: 'walkthrough-confirm.png' });
  const dismissed = page.locator('.review-grid > article').filter({ hasText: 'walkthrough-dismiss.png' });
  await expect(confirmed).toBeVisible();
  await expect(dismissed).toBeVisible();
  await confirmed.getByRole('button', { name: 'Confirm defect' }).click();
  await expect(confirmed).toHaveCount(0);
  await dismissed.getByRole('button', { name: 'Dismiss alarm' }).click();
  await expect(dismissed).toHaveCount(0);

  await expect.poll(async () => {
    const data = await (await page.request.get('http://127.0.0.1:8000/api/dashboard', { headers })).json();
    return [data.metrics.rejected, data.metrics.false_alarms];
  }, { timeout: 30000 }).toEqual([before.metrics.rejected + 1, before.metrics.false_alarms + 1]);

  await page.getByRole('button', { name: 'Dashboard' }).click();
  await expect(page.locator('.production-ledger article').filter({ hasText: 'Confirmed rejects' }))
    .toContainText(String(before.metrics.rejected + 1));
  await expect(page.locator('.production-ledger article').filter({ hasText: 'Dismissed alarms' }))
    .toContainText(String(before.metrics.false_alarms + 1));
  await expect(page.getByText('Simulated', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Line completed', { exact: true })).toBeVisible();
});
