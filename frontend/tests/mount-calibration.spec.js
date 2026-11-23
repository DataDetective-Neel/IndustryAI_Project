import {test, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

test('the four pictured layouts show verified mounting holes and hide rejected guesses', async ({page}) => {
  const root = path.resolve('..');
  const output = path.join(root, 'runs/mount-calibration');
  await fs.mkdir(output, {recursive:true});
  const report = [];
  await page.goto('http://127.0.0.1:8000/#lab');
  for (const name of ['HCCC5', 'ACCC5', 'HBCC5', 'BCCC5', 'BCCB5']) {
    const pending = page.waitForResponse(r => r.url().includes('/api/landmarks/') && r.request().method() === 'POST');
    await page.getByLabel('Reference photo', {exact:true}).setInputFiles(path.join(root, `PCB_Dataset_Pilot/images/train/${name}.jpg`));
    if (!(await page.getByRole('radio', {name:'Automatic', exact:true}).isChecked()))
      await page.getByRole('radio', {name:'Automatic', exact:true}).check();
    const result = await (await pending).json();
    report.push({image:name, result});
    if (name === 'BCCB5') {
      expect(result.status).toBe('failure');
      await expect(page.getByText('Landmarks need review.', {exact:true})).toBeVisible();
      await expect(page.locator('svg.photo-canvas circle')).toHaveCount(0);
      await page.getByRole('radio', {name:'Manual', exact:true}).check();
      await expect(page.getByLabel('upper_left_mount x', {exact:true})).toBeEditable();
      continue;
    }
    expect(result.status).toBe('ok');
    expect(result.source).toBe('calibrated_layout_mounts');
    const values = (await fs.readFile(path.join(root, `PCB_Dataset_Pilot/labels/train/${name}.txt`), 'utf8')).trim().split(/\s+/).map(Number);
    for (let i=0; i<4; i++) {
      const p = result.landmarks[i];
      expect(Math.hypot(p.x-values[5+i*3]*result.image_wh[0], p.y-values[6+i*3]*result.image_wh[1])).toBeLessThan(4);
    }
    await expect(page.getByText('Landmarks accepted', {exact:true})).toBeVisible();
    await expect(page.locator('svg.photo-canvas circle')).toHaveCount(4);
    await page.locator('svg.photo-canvas').screenshot({path:path.join(output, `${name}-app.png`)});
  }
  await fs.writeFile(path.join(output, 'browser-report.json'), JSON.stringify(report, null, 2));
});
