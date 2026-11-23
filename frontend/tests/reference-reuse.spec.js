import {test, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';

const root = path.resolve('..');
const output = path.join(root, 'runs/reference-reuse');
test.beforeAll(async () => {
  await fs.mkdir(output, {recursive:true});
  execFileSync(path.join(root,'.venv/Scripts/python.exe'), ['-c', `
import sys
sys.path.insert(0, 'tests')
from test_reference_reuse import board
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
out=Path('runs/reference-reuse')
a=board()
H=np.array([[.85,.08,25],[-.04,.88,30],[.00008,-.0001,1.]])
for name,image in [('reference',a),('same',a),('tilted',cv2.warpPerspective(a,H,(600,480))),('wrong',board(19)),('blank',np.full_like(a,120))]:
    Image.fromarray(image).save(out/(name+'.png'))
`], {cwd:root});
});

test('mark reference once after YOLO failure, reuse across views, and reset on replacement', async ({page}) => {
  await page.goto('/#lab');
  const refDetection=page.waitForResponse(r=>r.url().includes('/api/landmarks/') && r.request().method()==='POST');
  await page.getByLabel('Reference photo', {exact:true}).setInputFiles(path.join(output,'reference.png'));
  const detected=await (await refDetection).json();
  expect(detected.status).toBe('failure');
  expect(detected.reason).toContain('checkpoint_unavailable');
  await expect(page.getByLabel('upper_left_mount x', {exact:true})).toBeEditable();
  const names=['upper_left_mount','upper_right_mount','lower_right_mount','lower_left_mount'];
  const points=[[160,130],[440,130],[440,350],[160,350]];
  for (let i=0;i<4;i++) for (let j=0;j<2;j++)
    await page.getByLabel(`${names[i]} ${j?'y':'x'}`,{exact:true}).fill(String(points[i][j]));
  await page.getByRole('button',{name:'Mark PCB outline',exact:true}).click();
  const outlineNames=['outline upper left','outline upper right','outline lower right','outline lower left'];
  const polygon=[[45,35],[554,35],[554,444],[45,444]];
  for (let i=0;i<4;i++) for (let j=0;j<2;j++)
    await page.getByLabel(`${outlineNames[i]} ${j?'y':'x'}`,{exact:true}).fill(String(polygon[i][j]));
  const save=page.waitForResponse(r=>r.url().includes('/api/references/') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Confirm reference setup',exact:true}).click();
  expect((await (await save).json()).points).toEqual(points);
  await expect(page.getByRole('radio',{name:'Automatic',exact:true})).toBeChecked();
  await page.getByRole('button',{name:'Add box',exact:true}).click();
  await page.getByLabel('Inspection photos',{exact:true}).setInputFiles(['same','tilted','wrong','blank'].map(n=>path.join(output,n+'.png')));
  await expect(page.getByRole('button',{name:'Run Inspection',exact:true})).toBeEnabled();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/inspections') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Run Inspection',exact:true}).click();
  const report=await (await response).json();
  expect(report.photos.map(p=>p.components_evaluated)).toEqual([true,true,false,false]);
  for (const result of report.photos.slice(0,2)) {
    expect(result.landmark_diagnostics.inspection.reason).toContain('checkpoint_unavailable');
    expect(result.alignment.source).toBe('reference_registration');
    expect(result.alignment.landmark_kind).toBe('projected');
  }
  await expect(page.getByText('Registration: Needs review',{exact:true})).toHaveCount(2);
  const tiltedTab=page.getByRole('button').filter({has:page.locator('strong',{hasText:'tilted.png'})});
  await tiltedTab.click();
  await expect(page.locator('svg.photo-canvas text').filter({hasText:'projected'})).toHaveCount(4);
  await page.screenshot({path:path.join(output,'workflow.png'),fullPage:true});
  await fs.writeFile(path.join(output,'browser-report.json'),JSON.stringify(report,null,2));
  await page.getByTestId('result-2').getByRole('button',{name:'Switch to Manual',exact:true}).click();
  await expect(page.getByLabel('upper_left_mount x',{exact:true})).toBeEditable();
  await expect(page.getByRole('radio',{name:'Manual',exact:true})).toBeChecked();
  await page.getByRole('radio',{name:'Automatic',exact:true}).check();
  const replacement=page.waitForResponse(r=>r.url().endsWith('/automatic') && r.request().method()==='POST');
  await page.getByLabel('Reference photo',{exact:true}).setInputFiles(path.join(output,'wrong.png'));
  expect((await replacement).ok()).toBeTruthy();
  await expect(page.getByLabel('upper_left_mount x',{exact:true})).not.toHaveValue('');
  await expect(page.getByRole('button',{name:'Run Inspection',exact:true})).toBeDisabled();
  await expect(page.locator('svg.photo-canvas circle')).toHaveCount(4);
});
