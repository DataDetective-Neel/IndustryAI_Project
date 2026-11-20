export function imagePoint(clientX, clientY, rect, [width, height]) {
  return [
    Math.max(0, Math.min(width, ((clientX - rect.left) * width) / rect.width)),
    Math.max(
      0,
      Math.min(height, ((clientY - rect.top) * height) / rect.height),
    ),
  ];
}
export function pixelBox(start, end) {
  return [
    Math.floor(Math.min(start[0], end[0])),
    Math.floor(Math.min(start[1], end[1])),
    Math.ceil(Math.max(start[0], end[0])),
    Math.ceil(Math.max(start[1], end[1])),
  ];
}
