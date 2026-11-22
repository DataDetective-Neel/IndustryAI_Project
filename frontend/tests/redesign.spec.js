import { test, expect } from '@playwright/test';
import path from 'node:path';
const reference = path.resolve('../PCB_Dataset_Pilot/images/val/ECCC5.jpg');
const inspection = path.resolve('../PCB_Dataset_Pilot/images/val/ECCB5.jpg');

test('photo replacement and removal preserve the batch and reset reference annotations', async ({ page }) => {
  await page.goto('/#lab');
  await expect(page.getByText('Upload a known-good reference first.')).toBeVisible();
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(reference);
  await expect(page.getByRole('button', { name: 'Add box', exact: true })).toBeEnabled();
  await page.getByLabel('Inspection photos', { exact: true }).setInputFiles(inspection);
  await expect(page.getByRole('button', { name: /Inspection 1 ECCB5.jpg/ })).toBeVisible();
  await page.getByLabel('Replace ECCB5.jpg').setInputFiles(reference);
  await expect(page.getByRole('button', { name: /Inspection 1 ECCC5.jpg/ })).toBeVisible();
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(inspection);
  await expect(page.getByText(/component candidates proposed/i)).toBeVisible();
  await page.getByRole('button', { name: 'Remove ECCB5.jpg', exact: true }).click();
  await expect(page.getByText('Upload a known-good reference first.')).toBeVisible();
  await expect(page.getByRole('button', { name: /Inspection 1 ECCC5.jpg/ })).toBeVisible();
  await page.getByRole('button', { name: 'Remove ECCC5.jpg', exact: true }).click();
  await expect(page.getByRole('button', { name: /Inspection 1/ })).toHaveCount(0);
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('bad') });
  await expect(page.getByRole('alert')).toContainText('Choose a JPEG or PNG');
});

test('comparison uses returned outcomes, aligned opacity and finding coordinates', async ({ page }) => {
  await page.goto('/#lab');
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(reference);
  await expect(page.getByRole('button', { name: 'Add box', exact: true })).toBeEnabled();
  await page.getByLabel('Inspection photos', { exact: true }).setInputFiles(inspection);
  await expect(page.getByRole('button', { name: /Inspection 1 ECCB5.jpg/ })).toBeVisible();
  let outcome = 'missing';
  let aligned = true;
  await page.route('**/api/inspections', async (route) => {
    const request = route.request().postDataJSON();
    await route.fulfill({ json: {
      mode: 'manual', report_url: '/report', photos: [{
        photo_id: request.inspections[0].photo_id, filename: 'ECCB5.jpg', outcome,
        difference_overlay_url: aligned ? '/api/mock-difference' : null,
        alignment: aligned ? { status: 'ok', homography_inspection_to_reference: [[1,0,12],[0,1,24],[0,0,1]] } : { status: 'failure', reason: 'Mounting holes not verified' },
        components: [{ id: 'chip', name: 'Processor', status: outcome === 'missing' ? 'missing' : 'uncertain', display_status: outcome === 'missing' ? 'Missing' : 'Needs review', bbox_xyxy_px: [40,50,200,250], score: .2, overlap: .98, reason: 'Pipeline evidence', best_match_offset_px: [2,3] }],
      }],
    }});
  });
  await page.getByRole('button', { name: 'Run Inspection' }).click();
  const result = page.getByTestId('result-0');
  await expect(result.getByRole('button', { name: 'Side by side' })).toHaveAttribute('aria-pressed', 'true');
  await result.getByRole('button', { name: 'Processor Missing' }).click();
  await expect(result.locator('.finding-highlight.missing')).toHaveAttribute('x', '40');
  await result.getByRole('button', { name: 'Overlay', exact: true }).click();
  await result.getByRole('slider').fill('75');
  await expect(result.getByRole('img', { name: 'Aligned inspection', exact: true })).toHaveCSS('opacity', '0.75');
  await expect(result.getByRole('img', { name: 'Aligned inspection', exact: true })).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 12, 24)');
  await result.getByRole('button', { name: 'Difference', exact: true }).click();
  await expect(result.getByRole('img', { name: 'Difference heatmap for ECCB5.jpg' })).toBeVisible();
  await result.getByRole('button', { name: 'Overlay', exact: true }).click();
  for (const width of [1440, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(result.getByRole('slider')).toBeVisible();
    await expect(result.locator('.finding-highlight')).toBeVisible();
  }
  await result.getByText('Measurement details').click();
  await expect(result.getByText('2, 3', { exact: true })).toBeVisible();
  for (const value of ['review', 'DIFFERENT_BOARD', 'future_outcome']) {
    outcome = value; aligned = false;
    await page.getByRole('button', { name: 'Run Inspection' }).click();
    await expect(result.locator('.result-heading .status')).toHaveText(value === 'review' ? 'Needs review' : value === 'DIFFERENT_BOARD' ? 'Different board' : value);
    await expect(result.getByText('Mounting holes not verified')).toBeVisible();
    await expect(result.getByRole('button', { name: 'Overlay', exact: true })).toBeDisabled();
    await expect(result.getByText('Different board', { exact: true })).toHaveCount(value === 'DIFFERENT_BOARD' ? 1 : 0);
  }
});

test('empty state and landmark controls fit a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await page.goto('/#lab');
  await expect(page.getByRole('button', { name: 'Run Inspection' })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByLabel('Reference photo', { exact: true }).setInputFiles(reference);
  await expect(page.getByRole('button', { name: 'Add box', exact: true })).toBeEnabled();
  await page.getByLabel('upper_left_mount x', { exact: true }).fill('200');
  await page.getByLabel('upper_left_mount y', { exact: true }).fill('250');
  await expect(page.getByLabel('upper_left_mount x', { exact: true })).toHaveValue('200');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
