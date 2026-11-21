import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

test('wrong-board, blue-board angle controls, local absence and blur through the production UI', async ({page}) => {
  const root = path.resolve('..');
  const output = path.join(root, 'runs/board-compatibility');
  await fs.mkdir(output, {recursive:true});
  execFileSync(path.join(root,'.venv/Scripts/python.exe'), ['-c',
    "from PIL import Image,ImageFilter; from pathlib import Path; import numpy as np; p=Path('runs/board-compatibility'); a=np.array(Image.open('PCB_Dataset_Pilot/images/train/ACCC5.jpg').convert('RGB')); a[705:935,390:620]=(25,65,85); Image.fromarray(a).save(p/'SIMULATED-processor-absence.png'); Image.open('PCB_Dataset_Pilot/images/train/MBCC5.jpg').filter(ImageFilter.GaussianBlur(20)).save(p/'blurred.png')"], {cwd:root});
  const names = ['upper_left_mount','upper_right_mount','lower_right_mount','lower_left_mount'];
  async function mark(label) {
    const values=(await fs.readFile(path.join(root,`PCB_Dataset_Pilot/labels/train/${label}.txt`),'utf8')).trim().split(/\s+/).map(Number);
    const [, , width,height]=(await page.locator('svg.photo-canvas').getAttribute('viewBox')).split(/\s+/).map(Number);
    for(let i=0;i<4;i++) for(const [axis,side] of [['x',width],['y',height]])
      await page.getByLabel(`${names[i]} ${axis}`,{exact:true}).fill(String(values[5+i*3+(axis==='y'?1:0)]*side));
  }
  await page.goto('http://127.0.0.1:8000/');
  await page.getByLabel('Reference photo',{exact:true}).setInputFiles(path.join(root,'PCB_Dataset_Pilot/images/train/ACCC5.jpg'));
  await expect(page.getByRole('button',{name:'Add box',exact:true})).toBeEnabled();
  await mark('ACCC5');
  await page.getByRole('button',{name:'Add box',exact:true}).click();
  await page.getByLabel('Component name',{exact:true}).fill('Main processor');
  for(const [index,axis] of ['x1','y1','x2','y2'].entries())
    await page.getByLabel(`Region ${axis}`,{exact:true}).fill(String([390,705,620,935][index]));
  const sourceNames=['MBCC5','ABCC5','ACCB5','ACDC5','ADCC5'];
  const files=sourceNames.map(n=>path.join(root,`PCB_Dataset_Pilot/images/train/${n}.jpg`));
  files.push(path.join(output,'SIMULATED-processor-absence.png'),path.join(output,'blurred.png'));
  await page.getByLabel('Inspection photos',{exact:true}).setInputFiles(files);
  await expect(page.getByRole('button',{name:/Inspection 7 blurred.png/})).toBeVisible();
  for(let i=0;i<files.length;i++) {
    await page.getByRole('button',{name:new RegExp(`Inspection ${i+1} ${path.basename(files[i]).replaceAll('.','\\.')}`)}).click();
    await mark(i<5?sourceNames[i]:i===5?'ACCC5':'MBCC5');
  }
  await page.getByLabel('Label this run as a synthetic demonstration').check();
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/inspections') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Run Inspection',exact:true}).click();
  const batch=await (await pending).json();
  const wrong=batch.photos[0];
  expect(wrong.outcome).toBe('DIFFERENT_BOARD');
  expect(wrong.reason).toBe('Inspection board does not match the reference design.');
  expect(wrong.components).toEqual([]);
  expect(wrong.components_evaluated).toBe(false);
  await expect(page.getByTestId('result-0').getByText(wrong.reason,{exact:true})).toBeVisible();
  await expect(page.getByTestId('result-0').getByText('Main processor',{exact:true})).toHaveCount(0);
  await page.getByTestId('result-0').getByText('Board compatibility evidence',{exact:true}).click();
  await expect(page.getByTestId('result-0').locator('pre')).toContainText('micropcb_A');
  await expect(page.getByTestId('result-0').locator('pre')).toContainText('micropcb_M');
  for(const photo of batch.photos.slice(1,5)) {
    expect(photo.board_compatibility.status).toBe('SAME_DESIGN');
    expect(photo.components_evaluated).toBe(true);
    expect(photo.components[0].status).toBe('present');
  }
  expect(batch.photos[5].board_compatibility.status).toBe('SAME_DESIGN');
  expect(batch.photos[5].components_evaluated).toBe(true);
  expect(batch.photos[5].components[0].status).toBe('uncertain');
  expect(batch.photos[6].outcome).toBe('review');
  expect(batch.photos[6].components_evaluated).toBe(false);
  await fs.writeFile(path.join(output,'browser-report.json'),JSON.stringify(batch,null,2));
  await page.getByTestId('result-0').screenshot({path:path.join(output,'wrong-board.png')});
  await page.getByRole('radio',{name:'Automatic',exact:true}).check();
  await expect(page.getByText('Detecting landmarks with the local model…')).toHaveCount(0,{timeout:60000});
  const automaticPending=page.waitForResponse(r=>r.url().endsWith('/api/inspections') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Run Inspection',exact:true}).click();
  const automatic=await (await automaticPending).json();
  expect(automatic.photos[0].outcome).toBe('DIFFERENT_BOARD');
  for (const photo of automatic.photos.slice(1,5)) {
    expect(photo.board_compatibility.status).toBe('SAME_DESIGN');
    expect(photo.components_evaluated).toBe(true);
    expect(photo.components[0].status).toBe('present');
  }
  expect(automatic.photos[5].components_evaluated).toBe(true);
  await expect(page.getByTestId('result-0').getByRole('button',{name:'Switch to Manual',exact:true})).toHaveCount(0);
  await fs.writeFile(path.join(output,'browser-automatic-report.json'),JSON.stringify(automatic,null,2));
});
