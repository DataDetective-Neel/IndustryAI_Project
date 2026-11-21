import {confirmReference} from './reference-setup.js';
import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
const root = path.resolve('..');
const evidenceDir = path.join(root, 'runs/demo-evidence');
const names = ['upper_left_mount','upper_right_mount','lower_right_mount','lower_left_mount'];
async function mark(page, points) {
  for (let i=0;i<4;i++) for (const [j,axis] of ['x','y'].entries())
    await page.getByLabel(`${names[i]} ${axis}`,{exact:true}).fill(String(points[i][j]));
}
async function inspect(page) {
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/inspections') && r.request().method()==='POST');
  await page.getByRole('button',{name:"Run Inspection"}).click();
  return (await pending).json();
}
test('one-board real-photo fixtures through production upload and inspect UI', async ({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try { await fs.access(path.join(evidenceDir,'evidence.json')); }
  catch { execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-m','pcb_landmarks.demo_check'],{cwd:root}); }
  const evidence=JSON.parse(await fs.readFile(path.join(evidenceDir,'evidence.json'),'utf8'));
  await page.goto('http://127.0.0.1:8000/');
  await page.getByLabel('Reference photo',{exact:true}).setInputFiles(path.join(root,'PCB_Dataset_Pilot/images/val/ECCC5.jpg'));
  await expect(page.getByRole('button',{name:'U2 chip',exact:true})).toBeVisible();
  await mark(page,evidence.direct_vs_app.reference.labeled_points_px);
  await page.getByLabel('Inspection photos',{exact:true}).setInputFiles(['reference.png','mild-perspective.png','badly-cropped.png'].map(f=>path.join(evidenceDir,f)));
  const labels=['identical','mild_perspective','badly_cropped'];
  const files=['reference.png','mild-perspective.png','badly-cropped.png'];
  for(let i=0;i<3;i++) {
    await page.getByRole('button',{name:new RegExp(`Inspection ${i+1} ${files[i]}`)}).click();
    await mark(page,evidence.direct_vs_app[labels[i]].labeled_points_px);
  }
  await page.getByLabel('Label this run as a synthetic demonstration').check();
  const manual=await inspect(page);
  expect(manual.photos.map(p=>p.outcome)).toEqual(['ok','ok','review']);
  for(const photo of manual.photos.slice(0,2)) {
    expect(photo.components).toHaveLength(8);
    expect(photo.components.every(p=>p.status==='present')).toBe(true);
  }
  expect(manual.photos.flatMap(p=>p.components).filter(p=>p.status==='missing')).toHaveLength(0);
  await expect(page.getByTestId('result-1').getByText(/Alignment overlay score/)).toContainText('0.9990');
  await page.screenshot({path:path.join(evidenceDir,'browser-three-cases.png'),fullPage:true});
  // Run the simulated defect separately and label it clearly.
  for(const file of files) await page.getByRole('button',{name:`Remove ${file}`,exact:true}).click();
  await page.getByLabel('Inspection photos',{exact:true}).setInputFiles(path.join(evidenceDir,'SIMULATED-erasure.png'));
  await mark(page,evidence.direct_vs_app.SIMULATED_erasure.labeled_points_px);
  const simulated=await inspect(page);
  expect(simulated.synthetic).toBe(true);
  expect(simulated.photos[0].outcome).toBe('review');
  expect(simulated.photos[0].components.filter(p=>p.status==='present')).toHaveLength(7);
  await confirmReference(page, [[220,250],[1000,250],[1000,1390],[220,1390]]);
  await expect(page.getByText('Detecting landmarks with the local model…')).toHaveCount(0,{timeout:60000});
  await expect(page.getByText('Raw landmark diagnostics (rejected points are tentative)')).toBeVisible({timeout:60000});
  const automatic=await inspect(page);
  expect(automatic.photos[0].outcome).toBe('review');
  const health = await (await page.request.get('http://127.0.0.1:8000/api/health')).json();
  expect(automatic.photos[0].landmark_diagnostics.reference.status).toBe('confirmed');
  if (automatic.photos[0].alignment.status === 'ok') expect(automatic.photos[0].alignment.source).toBe('reference_registration');
  await page.screenshot({path:path.join(evidenceDir,'browser-automatic-review.png'),fullPage:true});
  await fs.writeFile(path.join(evidenceDir,'browser-evidence.json'),JSON.stringify({manual,simulated,automatic,errors},null,2));
  expect(errors).toEqual([]);
});
