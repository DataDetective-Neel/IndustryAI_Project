import {expect} from '@playwright/test';

export async function confirmReference(page, polygon) {
  await page.locator('.photo-tabs').getByRole('button', {name:/^Reference /}).click();
  await page.getByRole('button', {name:'Mark PCB outline',exact:true}).click();
  const names=['outline upper left','outline upper right','outline lower right','outline lower left'];
  for(let i=0;i<4;i++) for(let j=0;j<2;j++)
    await page.getByLabel(`${names[i]} ${j?'y':'x'}`,{exact:true}).fill(String(polygon[i][j]));
  const pending=page.waitForResponse(r=>r.url().includes('/api/references/') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Confirm reference setup',exact:true}).click();
  expect((await pending).status()).toBe(200);
}
