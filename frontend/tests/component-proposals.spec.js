import { test, expect } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs/promises';
import { confirmReference } from './reference-setup.js';

test.afterEach(async ({ page }) => {
  const token = await page.evaluate(() => localStorage.getItem('aoi_token')).catch(() => null);
  if (token) await page.request.delete('http://127.0.0.1:8000/api/golden-config', {
    headers: { Authorization: `Bearer ${token}` },
  });
});

test('golden upload proposes UNKNOWN component boxes without manual drawing', async ({ page }) => {
  await page.goto('/#lab');
  const pending = page.waitForResponse(response =>
    response.url().includes('/component-proposals') && response.request().method() === 'POST');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(
    path.resolve('..', 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  const response = await pending;
  expect(response.ok()).toBeTruthy();
  const proposal = await response.json();
  expect(proposal.verified).toBe(false);
  expect(proposal.components.length).toBeGreaterThanOrEqual(6);
  await expect(page.locator('rect.region-box')).toHaveCount(proposal.components.length);
  await expect(page.getByText(/component candidates proposed/i)).toBeVisible();
  await expect(page.locator('.part-list small').first()).toHaveText('UNKNOWN');

  const x1 = Number(await page.getByLabel('Region x1', { exact: true }).inputValue());
  await page.getByLabel('Component name', { exact: true }).fill('Verified component');
  await page.getByLabel('Region x1', { exact: true }).fill(String(x1 + 1));
  const values = (await fs.readFile(path.resolve('..', 'PCB_Dataset_Pilot/labels/val/ECCC5.txt'), 'utf8'))
    .trim().split(/\s+/).map(Number);
  const [, , width, height] = (await page.locator('svg.photo-canvas').getAttribute('viewBox')).split(/\s+/).map(Number);
  const names = ['upper_left_mount', 'upper_right_mount', 'lower_right_mount', 'lower_left_mount'];
  for (let i = 0; i < 4; i++) {
    await page.getByLabel(`${names[i]} x`, { exact: true }).fill(String(values[5+i*3] * width));
    await page.getByLabel(`${names[i]} y`, { exact: true }).fill(String(values[6+i*3] * height));
  }
  await confirmReference(page, [[221,115], [1002,115], [1002,1412], [221,1412]]);
  await expect(page.getByRole('button', { name: 'Save for live line', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Accept all proposals', exact: true }).click();
  const saved = page.waitForResponse(response => response.url().endsWith('/api/golden-config') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Save for live line', exact: true }).click();
  expect((await saved).ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByText('Saved golden configuration restored.')).toBeVisible();
  await expect(page.getByLabel('Component name', { exact: true })).toHaveValue('Verified component');
  await expect(page.getByLabel('Region x1', { exact: true })).toHaveValue(String(x1 + 1));
});
