import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

test('automatic landmarks sit on the Raspberry Pi mounting holes in the production app', async ({ page }) => {
  const root = path.resolve('..');
  const labels = (await fs.readFile(path.join(root, 'PCB_Dataset_Pilot/labels/train/MCCB5.txt'), 'utf8')).trim().split(/\s+/).map(Number);
  const pending = page.waitForResponse(r => r.url().includes('/api/landmarks/') && r.request().method() === 'POST');
  await page.goto('http://127.0.0.1:8000/');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(path.join(root, 'PCB_Dataset_Pilot/images/train/MCCB5.jpg'));
  await expect(page.getByRole('button', { name: 'Add box', exact: true })).toBeEnabled();
  await page.getByRole('radio', { name: 'Automatic', exact: true }).check();
  const result = await (await pending).json();
  expect(result.status).toBe('ok');
  expect(result.refinement.status).toBe('ok');
  expect(result.landmarks).toHaveLength(4);
  for (let i = 0; i < 4; i++) {
    const point = result.landmarks[i];
    expect(Math.hypot(point.x-labels[5+i*3]*1536, point.y-labels[6+i*3]*1533)).toBeLessThan(4);
  }
  await expect(page.getByText('Landmarks accepted', { exact: true })).toBeVisible();
  await expect(page.locator('svg.photo-canvas circle')).toHaveCount(4);
  await page.screenshot({path:path.join(root,'runs/landmarks/holes_finetune_20261121/browser-accepted.png'),fullPage:true});
});
