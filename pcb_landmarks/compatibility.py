"""Recognize supported layouts from distributed stable features, independently of component presence."""
import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .compare import _score
from .data import read_image, read_label


CATALOG = Path(__file__).resolve().parents[1]/'configs/board_designs.json'
MISMATCH_MESSAGE = 'Inspection board does not match the reference design.'


def _features(image, regions=None, polygon=None):
    image = np.asarray(image)
    scale = min(1, 1000/max(image.shape[:2]))
    gray = cv2.cvtColor(cv2.resize(image, None, fx=scale, fy=scale), cv2.COLOR_RGB2GRAY)
    mask = None
    if regions:
        mask = np.zeros(gray.shape, np.uint8)
        for region in regions:
            x1, y1, x2, y2 = np.round(np.array(region['box'])*scale).astype(int)
            mask[y1:y2, x1:x2] = 255
        board = np.zeros(gray.shape, np.uint8)
        cv2.fillConvexPoly(board, np.int32(np.round(np.array(polygon)*scale)), 255)
        # Keep cloth/background outside the PCB from contributing identity votes.
        mask = cv2.bitwise_and(mask, cv2.erode(board, np.ones((7, 7), np.uint8)))
    points, descriptors = cv2.SIFT_create(nfeatures=2200, contrastThreshold=.025).detectAndCompute(gray, mask)
    return points, descriptors, scale, gray


@lru_cache(maxsize=4)
def _profiles(catalog):
    path = Path(catalog)
    if not path.is_file():
        return []  # Manual/synthetic inspection remains usable without the source dataset.
    profiles = []
    for design in json.loads(path.read_text(encoding='utf-8'))['designs']:
        image_path, label_path = path.parent.parent/design['image'], path.parent.parent/design['label']
        if not image_path.is_file() or not label_path.is_file():
            continue
        image = read_image(image_path)
        points, descriptors, scale, _ = _features(image, design['regions'], design['board_polygon'])
        _, mounts = read_label(label_path)
        profiles.append(dict(design, keypoints=points, descriptors=descriptors, scale=scale,
                             mounts=mounts[:, :2]*image.size))
    return profiles


def identify_board(image, catalog=CATALOG):
    """Identify only with >=25 geometric inliers in >=3 separated stable layout regions."""
    image = np.asarray(image)
    points, descriptors, scale, gray = _features(image)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    base = dict(status='UNKNOWN', layout_id=None, matched_regions=[], sharpness=sharpness,
                method='SIFT ratio matches and RANSAC across stable layout regions')
    if sharpness < 12 or gray.std() < 5:
        return dict(base, status='REVIEW', reason='blur_or_insufficient_layout_detail')
    if descriptors is None or len(descriptors) < 25:
        return dict(base, reason='insufficient_positive_layout_evidence')
    accepted = []
    for profile in _profiles(str(catalog)):
        pairs = cv2.BFMatcher().knnMatch(profile['descriptors'], descriptors, k=2)
        matches = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .72*pair[1].distance]
        # A repeated pad/character in the inspection cannot vote multiple times.
        matches = list({m.trainIdx: m for m in sorted(matches, key=lambda m: -m.distance)}.values())
        if len(matches) < 25:
            continue
        source = np.float32([profile['keypoints'][m.queryIdx].pt for m in matches])
        target = np.float32([points[m.trainIdx].pt for m in matches])
        matrix, inlier_mask = cv2.findHomography(source, target, cv2.RANSAC, 3)
        if matrix is None or not np.isfinite(matrix).all():
            continue
        inliers = source[inlier_mask.ravel() > 0]/profile['scale']
        counts = [0]*len(profile['regions'])
        for x, y in inliers:
            for index, region in enumerate(profile['regions']):
                x1, y1, x2, y2 = region['box']
                if x1 <= x < x2 and y1 <= y < y2:
                    counts[index] += 1
                    break
        regions = [dict(name=r['name'], kind=r['kind'], inliers=count)
                   for r, count in zip(profile['regions'], counts) if count >= 5]
        polygon = np.float32(profile['board_polygon'])
        spread = cv2.contourArea(cv2.convexHull(inliers))/cv2.contourArea(polygon) if len(inliers) >= 3 else 0
        if len(inliers) < 25 or len(inliers)/len(matches) < .45 or len(regions) < 3 or spread < .12:
            continue
        matrix = np.diag([1/scale, 1/scale, 1]) @ matrix @ np.diag([profile['scale'], profile['scale'], 1])
        projected = cv2.perspectiveTransform(polygon[None], matrix)[0]
        if not np.isfinite(projected).all() or not cv2.isContourConvex(projected):
            continue
        frame = np.float32([[0, 0], [image.shape[1]-1, 0], [image.shape[1]-1, image.shape[0]-1], [0, image.shape[0]-1]])
        area = cv2.contourArea(projected)
        if area < .05*image.shape[0]*image.shape[1]:
            continue
        visible = float(np.clip(cv2.intersectConvexConvex(projected, frame)[0]/area, 0, 1))
        accepted.append(dict(base, status='IDENTIFIED', layout_id=profile['id'], name=profile['name'],
                             matched_regions=regions, inliers=len(inliers), match_count=len(matches),
                             spatial_coverage=float(spread), visible_fraction=visible,
                             template_to_image=matrix.tolist(),
                             template_controls=profile['mounts'].tolist() +
                                 [[(r['box'][0]+r['box'][2])/2, (r['box'][1]+r['box'][3])/2]
                                  for r in profile['regions']]))
    accepted.sort(key=lambda row: row['inliers'], reverse=True)
    if not accepted:
        return dict(base, reason='insufficient_positive_layout_evidence')
    if len(accepted) > 1 and accepted[0]['inliers'] < 1.5*accepted[1]['inliers']:
        return dict(base, status='REVIEW', reason='ambiguous_supported_layouts')
    result = accepted[0]
    if result['visible_fraction'] < .9:
        result.update(status='REVIEW', reason='board_layout_clipped')
    return result


def check_compatibility(reference_info, inspection_info, reference=None, aligned=None,
                        mask=None, homography=None, reference_points=None):
    result = dict(status='UNVERIFIED', message='Board layout needs review.',
                  reference=reference_info, inspection=inspection_info)
    if 'REVIEW' in [reference_info['status'], inspection_info['status']]:
        return dict(result, status='REVIEW', reason='blur_crop_or_ambiguous_layout',
                    message='Board layout needs review because of blur, clipping, or ambiguous evidence.')
    if reference_info['status'] == inspection_info['status'] == 'IDENTIFIED':
        if reference_info['layout_id'] != inspection_info['layout_id']:
            return dict(result, status='DIFFERENT_BOARD', message=MISMATCH_MESSAGE,
                        reason='different_positively_recognized_layouts')
        if aligned is None:
            return dict(result, status='SAME_DESIGN', message='Reference design recognized.')
        controls = np.float64(reference_info['template_controls'])[None]
        expected = cv2.perspectiveTransform(controls, np.array(reference_info['template_to_image']))[0]
        observed = cv2.perspectiveTransform(controls, np.array(inspection_info['template_to_image']))
        recovered = cv2.perspectiveTransform(observed, homography)[0]
        errors = np.linalg.norm(recovered-expected, axis=1)
        limit = max(8, .01*np.hypot(*np.asarray(reference).shape[:2]))
        evidence = dict(median_error_px=float(np.median(errors)), p90_error_px=float(np.percentile(errors, 90)),
                        tolerance_px=float(limit), method='independent distributed layout feature controls')
        if np.median(errors) > limit or np.percentile(errors, 90) > 2*limit:
            return dict(result, status='REVIEW', reason='uncertain_alignment', alignment_evidence=evidence,
                        message='Alignment is uncertain. Correct the landmarks or retake the image.')
        return dict(result, status='SAME_DESIGN', message='Reference design recognized.', alignment_evidence=evidence)
    if aligned is None:
        return result
    # Positive distributed agreement can support an uncatalogued/synthetic same-design pair.
    # Failure here never identifies a different board.
    reference, aligned = np.asarray(reference), np.asarray(aligned)
    points = np.asarray(reference_points)
    x1, y1 = np.floor(points.min(axis=0)).astype(int)
    x2, y2 = np.ceil(points.max(axis=0)).astype(int)
    rows = []
    for row in range(3):
        for column in range(3):
            left, right = np.linspace(x1, x2, 4).astype(int)[column:column+2]
            top, bottom = np.linspace(y1, y2, 4).astype(int)[row:row+2]
            coverage = float((mask[top:bottom, left:right] == 255).mean())
            score, _ = _score(reference[top:bottom, left:right], aligned[top:bottom, left:right], False)
            rows.append(dict(row=row, column=column, coverage=coverage, score=score,
                             matches=coverage >= .98 and score is not None and score >= .7))
    matching = [r for r in rows if r['matches']]
    positive = len(matching) >= 6 and len({r['row'] for r in matching}) >= 2 and len({r['column'] for r in matching}) >= 2
    return dict(result, status='SAME_DESIGN' if positive else 'REVIEW',
                message='Distributed layout agreement.' if positive else 'Board layout or alignment needs review.',
                reason='distributed_positive_agreement' if positive else 'insufficient_positive_layout_evidence', regions=rows)
