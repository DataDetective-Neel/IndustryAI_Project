import { test, expect } from '@playwright/test';
import path from 'node:path';

const fixture = path.resolve('..', 'PCB_Dataset_Pilot/images/val/ECCC5.jpg');

test('drag release and access navigation do not raise page errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));

  await page.goto('/#lab');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(fixture);
  const box = page.locator('rect.region-box').first();
  await expect(box).toBeVisible();
  const bounds = await box.boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2 + 8, bounds.y + bounds.height / 2 + 8);
  await page.mouse.up();
  await expect(page.getByLabel('Component name', { exact: true })).toBeVisible();

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.getByRole('button', { name: 'Access Management' }).click();
    await expect(page.getByRole('heading', { name: 'Access management' })).toBeVisible();
    await page.getByRole('button', { name: 'Dashboard' }).click();
    await expect(page.getByRole('heading', { name: 'Production overview' })).toBeVisible();
  }

  expect(errors).toEqual([]);
});

test('invalid golden replacement keeps the current reference and explains the error', async ({ page }) => {
  await page.goto('/#lab');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(fixture);
  await expect(page.getByAltText('Known-good reference preview')).toBeVisible();
  const original = await page.getByAltText('Known-good reference preview').getAttribute('src');

  await page.getByLabel('Reference photo', { exact: true }).setInputFiles({
    name: 'not-an-image.png',
    mimeType: 'image/png',
    buffer: Buffer.from('invalid image data'),
  });

  await expect(page.getByRole('alert')).toContainText('not-an-image.png');
  await expect(page.getByAltText('Known-good reference preview')).toHaveAttribute('src', original);
});
