import {test, expect} from '@playwright/test';
import path from 'node:path';

test('automatic ELEGOO setup, imported map, registered defect and persisted results', async ({page}) => {
  const dataset = process.env.PCB_REPAIR_DATASET || 'A:/IndustryAI_Dataset_Worktree/dataset_generation';
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/#lab');
  await page.getByLabel('Password', {exact:true}).fill('repair-browser-test-password');
  await page.getByLabel('Username', {exact:true}).fill('repair');
  await page.getByRole('button', {name:'Open AOI console'}).click();
  await expect(page.getByRole('radio', {name:'Automatic', exact:true})).toBeChecked();
  const setupResponse = page.waitForResponse(r => r.url().endsWith('/automatic') && r.request().method() === 'POST');
  await page.getByLabel('Reference photo', {exact:true}).setInputFiles(path.join(dataset,'golden/golden_reference.png'));
  expect((await setupResponse).ok()).toBeTruthy();
  await expect(page.locator('svg.photo-canvas polygon')).toHaveCount(0);
  await expect(page.getByRole('button', {name:'Detect components',exact:true})).toBeEnabled();
  const imported = page.waitForResponse(r => r.url().endsWith('/component-map'));
  await page.getByLabel('Import Antigravity component map').setInputFiles(path.join(dataset,'golden/golden_components.json'));
  const map = await (await imported).json();
  expect(map.components).toHaveLength(34);
  await page.getByRole('button', {name:'Accept all proposals',exact:true}).click();
  const saved = page.waitForResponse(r => r.url().endsWith('/api/golden-config') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'Save for live line',exact:true}).click();
  expect((await saved).ok()).toBeTruthy();
  await page.getByLabel('Inspection photos', {exact:true}).setInputFiles(path.join(dataset,'images/misaligned/misaligned_002.png'));
  await expect(page.getByLabel('Inspection workspace overview')).toBeVisible();
  const inspectionResponse = page.waitForResponse(r => r.url().endsWith('/api/inspections') && r.request().method() === 'POST');
  await page.getByRole('button', {name:'Run Inspection',exact:true}).click();
  const batch = await (await inspectionResponse).json();
  const result = batch.photos[0];
  expect(result.alignment.status).toBe('ok');
  expect(result.components.filter(p => p.status === 'misaligned').map(p => p.id)).toEqual(['U2']);
  expect(result.components.filter(p => p.status === 'present')).toHaveLength(33);
  const report = await page.request.get(batch.report_url);
  expect((await report.json()).photos[0].components).toEqual(result.components);
  const sheet = page.getByTestId('result-0');
  await expect(sheet.getByRole('img', {name:'Registered findings for misaligned_002.png'}).locator('rect.misaligned')).toHaveCount(1);
  await expect(sheet.getByText('Registration: Verified', {exact:true})).toBeVisible();
  for (const label of ['Reference', 'Inspection', 'Overlay', 'Difference', 'Side by side']) {
    await sheet.getByRole('button', {name:label,exact:true}).click();
  }
  await sheet.getByText('Registration diagnostics', {exact:true}).click();
  await expect(sheet.locator('.registration-diagnostics pre')).toContainText('median_error_px');
  await expect(sheet.locator('.registration-diagnostics pre')).toContainText('mounting_holes_not_verified');
  const color = await page.locator('.annotation-panel').evaluate(el => ({
    background: getComputedStyle(el).backgroundColor,
    surface: getComputedStyle(el).getPropertyValue('--surface').trim(),
    ink: getComputedStyle(el).getPropertyValue('--ink').trim(),
  }));
  expect(color.surface).toMatch(/^#fff(?:fff)?$/);
  expect(color.ink).toBe('#172426');
  await page.screenshot({path:'../runs/repair-browser/inspection-lab.png', fullPage:true});
  await sheet.locator('.registration-diagnostics summary').click();
  await sheet.screenshot({path:'../runs/repair-browser/findings.png'});
  await page.getByLabel('Inspection workspace overview').screenshot({path:'../runs/repair-browser/workspace.png'});
  expect(errors).toEqual([]);
  await page.reload();
  await expect(page.getByText('Saved golden configuration restored.')).toBeVisible();
  await expect(page.locator('.part-list button')).toHaveCount(34);
});

test('Live Inspection uploads, previews, replaces and uses a golden reference', async ({page}) => {
  const dataset = process.env.PCB_REPAIR_DATASET || 'A:/IndustryAI_Dataset_Worktree/dataset_generation';
  await page.goto('/#live');
  await page.getByLabel('Password', {exact:true}).fill('repair-browser-test-password');
  await page.getByLabel('Username', {exact:true}).fill('repair');
  await page.getByRole('button', {name:'Open AOI console'}).click();
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/simulation/reference') && r.request().method()==='POST');
  await page.getByLabel('Upload Golden Reference', {exact:true}).setInputFiles(path.join(dataset,'golden/golden_reference.png'));
  const first=await (await pending).json();
  expect(first.components.length).toBeGreaterThan(20);
  expect(first.reference.points).toHaveLength(4);
  await expect(page.getByAltText('Active golden reference')).toBeVisible();
  await expect(page.getByAltText('Active golden reference')).toHaveAttribute('src',first.reference.image_url);
  const imported=page.waitForResponse(r=>r.url().endsWith('/api/simulation/import'));
  await page.getByLabel('Import inspection images', {exact:true}).setInputFiles(path.join(dataset,'golden/golden_reference.png'));
  expect((await imported).ok()).toBeTruthy();
  await page.getByRole('button',{name:'Start simulation',exact:true}).click();
  await expect.poll(async()=>{
    const token=await page.evaluate(()=>localStorage.getItem('aoi_token'));
    const response=await page.request.get('/api/simulation',{headers:{Authorization:`Bearer ${token}`}});
    return (await response.json()).last_result;
  },{timeout:45000}).toMatchObject({golden_reference_id:first.reference_id,alignment:{status:'ok'}});
  await expect(page.getByRole('button',{name:'Start simulation',exact:true})).toBeEnabled({timeout:15000});
  const replaced=page.waitForResponse(r=>r.url().endsWith('/api/simulation/reference') && r.request().method()==='POST');
  await page.getByLabel('Upload Golden Reference', {exact:true}).setInputFiles(path.join(dataset,'golden/golden_reference.png'));
  const second=await (await replaced).json();
  expect(second.reference_id).not.toBe(first.reference_id);
  await expect(page.getByAltText('Active golden reference')).toHaveAttribute('src',second.reference.image_url);
  await page.screenshot({path:'../runs/repair-browser/live-golden.png',fullPage:true});
});
