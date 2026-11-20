import test from "node:test";
import assert from "node:assert/strict";
import { imagePoint, pixelBox } from "./coordinates.js";

test("preview resizing maps a click to the same original pixel", () => {
  assert.deepEqual(
    imagePoint(
      150,
      250,
      { left: 50, top: 50, width: 400, height: 800 },
      [1000, 2000],
    ),
    [250, 500],
  );
  assert.deepEqual(
    imagePoint(
      100,
      150,
      { left: 50, top: 50, width: 200, height: 400 },
      [1000, 2000],
    ),
    [250, 500],
  );
});
test("coordinates stay inside the raster and boxes round outwards once", () => {
  assert.deepEqual(
    imagePoint(
      -50,
      900,
      { left: 0, top: 0, width: 200, height: 400 },
      [1000, 2000],
    ),
    [0, 2000],
  );
  assert.deepEqual(pixelBox([80.8, 90.1], [10.2, 20.5]), [10, 20, 81, 91]);
});
