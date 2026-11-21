// CSS uses column-major order; the API homography maps inspection pixels to reference pixels.
export function homographyTransform(matrix) {
  if (!Array.isArray(matrix) || matrix.length !== 3 || matrix.some((row) => !Array.isArray(row) || row.length !== 3 || !row.every(Number.isFinite))) return null;
  const [[a, b, c], [d, e, f], [g, h, i]] = matrix;
  if (Math.abs(a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)) < 1e-12) return null;
  return `matrix3d(${[a, d, 0, g, b, e, 0, h, 0, 0, 1, 0, c, f, 0, i].join(',')})`;
}

export function findingBox(box, width, height) {
  return Array.isArray(box) && box.length === 4 && box.every(Number.isFinite)
    && box[0] >= 0 && box[1] >= 0 && box[2] > box[0] && box[3] > box[1]
    && box[2] <= width && box[3] <= height ? box : null;
}
