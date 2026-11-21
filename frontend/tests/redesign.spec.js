import { test, expect } from '@playwright/test';
import path from 'node:path';
const reference = path.resolve('../PCB_Dataset_Pilot/images/val/ECCC5.jpg');
const inspection = path.resolve('../PCB_Dataset_Pilot/images/val/ECCB5.jpg');

test('photo replacement and removal preserve the batch and reset reference annotations', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Upload a known-good reference first.')).toBeVisible();
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(reference);
  await expect(page.getByRole('button', { name: 'Add box', exact: true })).toBeEnabled();
  await page.getByLabel('Inspection photos', { exact: true }).setInputFiles(inspection);
  await expect(page.getByRole('button', { name: /Inspection 1 ECCB5.jpg/ })).toBeVisible();
  await page.getByLabel('Replace ECCB5.jpg').setInputFiles(reference);
  await expect(page.getByRole('button', { name: /Inspection 1 ECCC5.jpg/ })).toBeVisible();
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(inspection);
  await expect(page.getByText('Draw or add an expected component box on the reference.')).toBeVisible();
  await page.getByRole('button', { name: 'Remove ECCB5.jpg', exact: true }).click();
  await expect(page.getByText('Upload a known-good reference first.')).toBeVisible();
  await expect(page.getByRole('button', { name: /Inspection 1 ECCC5.jpg/ })).toBeVisible();
  await page.getByRole('button', { name: 'Remove ECCC5.jpg', exact: true }).click();
  await expect(page.getByRole('button', { name: /Inspection 1/ })).toHaveCount(0);
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('bad') });
  await expect(page.getByRole('alert')).toContainText('Choose a JPEG or PNG');
});
