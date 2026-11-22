import { test, expect } from '@playwright/test';
import path from 'node:path';

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
  await expect(page.getByLabel('Component name', { exact: true })).toHaveValue(/UNKNOWN/);
});
