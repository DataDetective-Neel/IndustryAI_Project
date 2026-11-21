import test from 'node:test';
import assert from 'node:assert/strict';
import { findingBox, homographyTransform } from './comparison.js';

test('homography preserves translation and perspective in CSS column order', () => {
  const h = [[1.2, .1, 12], [.2, .9, 24], [.001, .002, 1]];
  const css = homographyTransform(h).slice(9, -1).split(',').map(Number);
  for (const [x, y] of [[0, 0], [40, 60], [320, 240]]) {
    const w = css[3] * x + css[7] * y + css[15];
    assert.equal((css[0] * x + css[4] * y + css[12]) / w, (h[0][0] * x + h[0][1] * y + h[0][2]) / (h[2][0] * x + h[2][1] * y + h[2][2]));
    assert.equal((css[1] * x + css[5] * y + css[13]) / w, (h[1][0] * x + h[1][1] * y + h[1][2]) / (h[2][0] * x + h[2][1] * y + h[2][2]));
  }
});

test('invalid homographies and out-of-bounds findings are not displayed', () => {
  for (const h of [null, [], [[0,0,0],[0,0,0],[0,0,0]], [[1,0,0],[0,1,0],[0,0,NaN]]]) assert.equal(homographyTransform(h), null);
  assert.deepEqual(findingBox([10,20,40,60], 100, 100), [10,20,40,60]);
  for (const b of [null, [-1,0,10,10], [20,20,10,10], [0,0,101,50], [0,0,NaN,20]]) assert.equal(findingBox(b,100,100), null);
});
