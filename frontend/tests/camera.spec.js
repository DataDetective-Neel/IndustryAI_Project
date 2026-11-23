import { test, expect } from '@playwright/test';
import path from 'node:path';

test('camera handles denied access without leaving a stale result', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      value: async () => { throw new DOMException('Camera permission denied', 'NotAllowedError'); },
    });
  });
  await page.goto('/#live');
  const uploaded = page.waitForResponse(r => r.url().endsWith('/api/simulation/reference') && r.request().method() === 'POST');
  await page.getByLabel('Upload Golden Reference').setInputFiles(
    path.resolve('..', 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  await uploaded;
  await expect(page.getByAltText('Active golden reference')).toBeVisible({ timeout: 60000 });
  await page.getByRole('button', { name: 'Start camera', exact: true }).click();
  await expect(page.locator('.platform-alert')).toContainText('Camera permission denied');
  await expect(page.getByRole('button', { name: 'Start camera', exact: true })).toBeEnabled();
  await expect(page.getByAltText('Camera inspection result')).toHaveCount(0);
});

test('camera captures original video dimensions and submits the selected reference', async ({ page }) => {
  await page.addInitScript(() => {
    const capture = HTMLCanvasElement.prototype.captureStream;
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 480;
      canvas.getContext('2d').fillRect(0, 0, 640, 480);
      window.cameraTestCanvas = canvas;
      return capture.call(canvas, 5);
    }});
  });
  await page.goto('/#live');
  const uploaded = page.waitForResponse(r => r.url().endsWith('/api/simulation/reference') && r.request().method() === 'POST');
  await page.getByLabel('Upload Golden Reference').setInputFiles(
    path.resolve('..', 'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  const selected = (await (await uploaded).json()).reference_id;
  await expect(page.getByAltText('Active golden reference')).toBeVisible({ timeout: 60000 });
  // Transport is intercepted here; the backend camera test exercises real registration.
  let submitted;
  await page.route('**/api/live/frame', async route => {
    submitted = route.request().postDataBuffer().toString('latin1');
    await route.fulfill({ json: { golden_reference_id: selected, outcome: 'review',
      reason: 'Synthetic camera transport fixture', components: [] } });
  });
  await page.getByRole('button', { name: 'Start camera', exact: true }).click();
  await expect.poll(() => submitted).toContain(selected);
  expect(submitted).toContain('camera.png');
  expect(await page.locator('video').evaluate(video => [video.videoWidth, video.videoHeight])).toEqual([640, 480]);
  await page.getByRole('button', { name: 'Stop camera', exact: true }).click();
  await expect(page.locator('video')).toHaveCount(0);
});
