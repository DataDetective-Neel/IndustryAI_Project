"""Align same-layout PCB photos from four ordered landmarks; no model required."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .data import read_image, read_label


def label_points(path, size):
    """Convert reviewed Step 2 labels to pixels in the actual decoded raster."""
    _, points = read_label(path)
    if (points[:, 2] != 2).any():
        raise ValueError(f'{Path(path).name}: all four landmarks must be visible (visibility 2)')
    return points[:, :2] * size


def _points(points, image, name):
    points = np.asarray(points, dtype=np.float64)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError(f'{name}: expected four finite ordered (x,y) pixel coordinates')
    height, width = image.shape[:2]
    if (points < 0).any() or (points[:, 0] >= width).any() or (points[:, 1] >= height).any():
        raise ValueError(f'{name}: landmarks outside decoded image bounds')
    distances = np.linalg.norm(points[:, None] - points[None, :], axis=2)
    if distances[np.triu_indices(4, 1)].min() < 1:
        raise ValueError(f'{name}: duplicate or near-duplicate landmarks (less than 1 pixel apart)')
    edges = np.roll(points, -1, axis=0) - points
    turns = edges[:, 0] * np.roll(edges, -1, axis=0)[:, 1] - edges[:, 1] * np.roll(edges, -1, axis=0)[:, 0]
    # Positive turns preserve dataset identities even when the board is rotated.
    if (turns <= 0).any():
        raise ValueError(f'{name}: crossed, concave, mirrored or incorrect landmark order')
    for i in range(4):
        others = np.delete(points, i, axis=0)
        a, b = others[1:] - others[0]
        altitude = abs(a[0]*b[1] - a[1]*b[0]) / max(
            np.linalg.norm(a), np.linalg.norm(b), np.linalg.norm(a-b))
        if altitude < max(1, .001 * np.hypot(width, height)):
            raise ValueError(f'{name}: nearly collinear landmarks')
    return points


def align_images(reference, inspection, reference_points, inspection_points):
    """Return (aligned RGB uint8, H_inspection_to_reference, uint8 validity mask).

    Images are decoded RGB uint8 arrays; points are (4,2) pixel arrays in fixed
    dataset order. Future inference callers can pass [[p['x'], p['y']], ...]
    from an accepted detection without normalization or reordering.
    Mask 255 means full bilinear source support; 0 must be excluded downstream.
    Raises ValueError for rejected geometry or an unusable transform.
    """
    reference, inspection = np.asarray(reference), np.asarray(inspection)
    for name, image in [('reference', reference), ('inspection', inspection)]:
        if image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 2 or image.dtype != np.uint8:
            raise ValueError(f'{name}: expected nonempty decoded RGB uint8 image at least 2x2')
    rp = _points(reference_points, reference, 'reference')
    ip = _points(inspection_points, inspection, 'inspection')
    homography = cv2.getPerspectiveTransform(ip.astype(np.float32), rp.astype(np.float32),
                                           solveMethod=cv2.DECOMP_SVD)
    rh, rw = reference.shape[:2]
    ih, iw = inspection.shape[:2]
    # Condition the test in image-relative coordinates, independent of resolution.
    normalized = np.diag([1/rw, 1/rh, 1]) @ homography @ np.diag([iw, ih, 1])
    if not np.isfinite(homography).all() or np.linalg.cond(normalized) > 1e8:
        raise ValueError('Unusable homography: nonfinite or ill-conditioned transform')
    corners = np.array([[0, 0, 1], [iw-1, 0, 1], [iw-1, ih-1, 1], [0, ih-1, 1]])
    denominators = corners @ homography[2]
    if not ((denominators > 0).all() or (denominators < 0).all()):
        raise ValueError('Unusable homography: projective horizon crosses inspection image')
    recovered = cv2.perspectiveTransform(ip[None], homography)[0]
    if not np.isfinite(recovered).all() or np.linalg.norm(recovered - rp, axis=1).max() > .1:
        raise ValueError('Unusable homography: landmark reprojection exceeds 0.1 pixel')
    aligned = cv2.warpPerspective(inspection, homography, (rw, rh), flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    support = cv2.warpPerspective(np.ones((ih, iw), np.float32), homography, (rw, rh),
                                 flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    # Nearest-neighbor alone can admit pixels blended with the artificial border.
    yy, xx = np.indices((rh, rw), dtype=np.float64)
    inverse = np.linalg.inv(homography)
    denominator = inverse[2, 0]*xx + inverse[2, 1]*yy + inverse[2, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        sx = (inverse[0, 0]*xx + inverse[0, 1]*yy + inverse[0, 2]) / denominator
        sy = (inverse[1, 0]*xx + inverse[1, 1]*yy + inverse[1, 2]) / denominator
    # Also exclude coordinates rounded onto the border by OpenCV's sampling table.
    inside = (sx >= -1e-7) & (sx <= iw-1+1e-7) & (sy >= -1e-7) & (sy <= ih-1+1e-7)
    mask = np.where((support >= 1 - 1e-6) & inside, 255, 0).astype(np.uint8)
    if not mask.any():
        raise ValueError('Unusable homography: no valid overlap in reference grid')
    return aligned, homography, mask


def blend_overlay(reference, aligned, mask):
    """50/50 blend in valid overlap; magenta hatching outside it (RGB)."""
    overlay = cv2.addWeighted(reference, .5, aligned, .5, 0)
    yy, xx = np.indices(mask.shape)
    invalid = mask == 0
    overlay[invalid] = (reference[invalid].astype(np.uint16) // 3).astype(np.uint8)
    overlay[invalid & ((xx + yy) % 16 < 5)] = (255, 0, 255)
    return overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--inspection', required=True)
    parser.add_argument('--reference-label', required=True, help='Step 2 YOLO Pose .txt')
    parser.add_argument('--inspection-label', required=True, help='Step 2 YOLO Pose .txt')
    parser.add_argument('--output', required=True, help='New local output directory (must not exist)')
    args = parser.parse_args()
    try:
        reference, inspection = read_image(args.reference), read_image(args.inspection)
        rp = label_points(args.reference_label, reference.size)
        ip = label_points(args.inspection_label, inspection.size)
        aligned, homography, mask = align_images(reference, inspection, rp, ip)
        overlay = blend_overlay(np.asarray(reference), aligned, mask)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        result = dict(status='ok', reason=None, landmark_source='reviewed_step2_labels',
                      coordinate_system='decoded_reference_pixels',
                      reference_wh=list(reference.size), inspection_wh=list(inspection.size),
                      homography_inspection_to_reference=homography.tolist(),
                      valid_overlap_fraction=float(np.count_nonzero(mask) / mask.size),
                      outputs={name: str((output / filename).resolve()) for name, filename in
                               [('aligned', 'aligned.png'), ('overlay', 'overlay.png'),
                                ('mask', 'overlap_mask.png')]})
        for name, image in [('aligned', aligned), ('overlay', overlay), ('mask', mask)]:
            Image.fromarray(image).save(result['outputs'][name])
        (output / 'alignment.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except (OSError, ValueError, cv2.error, np.linalg.LinAlgError) as error:
        result = dict(status='failure', reason=f'{type(error).__name__}: {error}')
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if result['status'] == 'ok' else 2)


if __name__ == '__main__':
    main()
