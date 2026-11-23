"""Offline registration against a user-confirmed reference, without a board catalog."""
import cv2
import numpy as np
from itertools import combinations

from .align import _points, align_images


def board_polygon(image):
    """Conservative proposal for colored solder mask; operator can correct the outline."""
    rgb = np.asarray(image)
    scale = min(1., 1000/max(rgb.shape[:2]))
    small = cv2.resize(rgb, None, fx=scale, fy=scale)
    # shortcut: colored convex solder mask; broaden segmentation for pale/black boards or colored clutter.
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (0, 45, 25), (179, 255, 245))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError('PCB surface not found; mark its outline separately from the landmarks.')
    contour = max(contours, key=cv2.contourArea)
    polygon = cv2.approxPolyDP(cv2.convexHull(contour), .015*cv2.arcLength(contour, True), True)
    if cv2.contourArea(polygon) < .15*mask.size or not 3 <= len(polygon) <= 12:
        raise ValueError('PCB surface is ambiguous; mark its outline or retake the photo.')
    return (polygon[:, 0]/scale).tolist()


def surface_mask(image, polygon):
    rgb = np.asarray(image)
    p = np.asarray(polygon, np.float32)
    if p.ndim != 2 or p.shape[1] != 2 or not 3 <= len(p) <= 12 or not np.isfinite(p).all():
        raise ValueError('PCB outline must contain 3 to 12 finite ordered points.')
    height, width = rgb.shape[:2]
    if (p < 0).any() or (p[:, 0] >= width).any() or (p[:, 1] >= height).any():
        raise ValueError('PCB outline is outside the original image.')
    if not cv2.isContourConvex(p) or cv2.contourArea(p) < .02*width*height:
        raise ValueError('PCB outline must be a non-crossing convex surface with usable area.')
    mask = np.zeros((height, width), np.uint8)
    cv2.fillConvexPoly(mask, np.round(p).astype(np.int32), 255)
    # Exclude the board edge and the adjacent background from feature evidence.
    radius = max(3, round(.008*min(height, width)))
    return cv2.erode(mask, np.ones((2*radius+1, 2*radius+1), np.uint8))


def mounting_centers(image, polygon):
    """Conservative circular bare-hole proposals, independent of pose predictions."""
    rgb = np.asarray(image)
    scale = min(1., 1000/max(rgb.shape[:2]))
    small = cv2.resize(rgb, None, fx=scale, fy=scale)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    neutral = cv2.inRange(hsv, (0, 0, 25), (179, 80, 255))
    neutral = cv2.morphologyEx(neutral, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    neutral = cv2.morphologyEx(neutral, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
    board = np.zeros(neutral.shape, np.uint8)
    cv2.fillConvexPoly(board, np.int32(np.asarray(polygon)*scale), 255)
    contours, _ = cv2.findContours(neutral & board, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    holes = []
    side = min(neutral.shape)
    angles = np.linspace(0, 2*np.pi, 64, endpoint=False)
    for contour in contours:
        area, perimeter = cv2.contourArea(contour), cv2.arcLength(contour, True)
        if len(contour) < 5 or perimeter == 0 or 4*np.pi*area/perimeter**2 < .7:
            continue
        (x,y),(w,h),_ = cv2.fitEllipse(contour)
        if not (.025*side < min(w,h) <= max(w,h) < .06*side) or min(w,h)/max(w,h) < .8:
            continue
        xs = np.clip((x+.8*max(w,h)*np.cos(angles)).astype(int), 0, small.shape[1]-1)
        ys = np.clip((y+.8*max(w,h)*np.sin(angles)).astype(int), 0, small.shape[0]-1)
        if (hsv[ys,xs,1] > 80).mean() < .6:
            continue  # Neutral components/buttons lack a surrounding solder-mask ring.
        point = np.array([x,y])/scale
        if all(np.linalg.norm(point-other) > .4*max(w,h)/scale for other in holes):
            holes.append(point)
    # Threshold blobs can join a hole to adjacent connector/silkscreen pixels.
    # Closed circular edges recover that geometry without using component boxes.
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    circles = cv2.HoughCircles(cv2.GaussianBlur(gray, (5,5), 1), cv2.HOUGH_GRADIENT_ALT,
        1., max(10, .025*side), param1=200, param2=.9,
        minRadius=max(5, round(.012*side)), maxRadius=max(6, round(.03*side)))
    for x, y, radius in ([] if circles is None else circles[0]):
        if cv2.pointPolygonTest(np.float32(polygon)*scale, (float(x), float(y)), False) < 0:
            continue
        def sample(factor):
            xs = np.clip(np.rint(x+factor*radius*np.cos(angles)).astype(int), 0, small.shape[1]-1)
            ys = np.clip(np.rint(y+factor*radius*np.sin(angles)).astype(int), 0, small.shape[0]-1)
            return hsv[ys, xs, 1]
        left, top = max(0, int(x-radius)), max(0, int(y-radius))
        right, bottom = min(gray.shape[1], int(x+radius)+1), min(gray.shape[0], int(y+radius)+1)
        yy, xx = np.mgrid[top:bottom, left:right]
        interior = gray[top:bottom, left:right][(xx-x)**2+(yy-y)**2 < (.65*radius)**2]
        if ((sample(.55) < 80).mean() < .9 or (sample(1.25) > 80).mean() < .6
                or not interior.size or interior.std() > 45):
            continue
        point = np.array([x,y])/scale
        if all(np.linalg.norm(point-other) > radius/scale for other in holes):
            holes.append(point)
    return holes


def automatic_reference(image):
    """Use board geometry as reference coordinates, never component centers.

    These points define a coordinate frame; inspection correspondences are
    independently recovered from distributed RANSAC matches.
    """
    polygon = board_polygon(image)
    holes = mounting_centers(image, polygon)
    if 4 <= len(holes) <= 16:
        choices = []
        for group in combinations(holes,4):
            hull = cv2.convexHull(np.float32(group))[:,0]
            if len(hull) == 4:
                choices.append((cv2.contourArea(hull), hull))
        if choices:
            area, contour = max(choices, key=lambda row: row[0])
            if area >= .2*cv2.contourArea(np.float32(polygon)):
                center = contour.mean(axis=0)
                points = contour[np.argsort(np.arctan2(contour[:,1]-center[1],contour[:,0]-center[0]))]
                points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
                _points(points, np.asarray(image), 'reference mounting centers')
                features = reference_features(image, polygon)
                if len(features['xy']) >= 35:
                    return dict(points=points.tolist(),board_polygon=polygon,confirmed=True,
                        source='opencv_mounting_centers',landmark_kind='mounting_holes',
                        coordinate_system='decoded_original_image_pixels',feature_count=len(features['xy']))
    contour = np.float32(polygon)
    if len(contour) != 4:
        # Chamfers and connectors can add outline vertices. Fit a board frame,
        # then keep every coordinate anchor inside the observed surface.
        contour = cv2.boxPoints(cv2.minAreaRect(contour))
    # Order clockwise in image coordinates, starting nearest the upper-left.
    center = contour.mean(axis=0)
    order = np.argsort(np.arctan2(contour[:, 1]-center[1], contour[:, 0]-center[0]))
    points = contour[order]
    points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
    # Inset boundary points to avoid rounding outside the segmented surface.
    for inset in (.96, .9, .8, .7):
        candidate = center + inset*(points-center)
        if all(cv2.pointPolygonTest(np.float32(polygon), tuple(map(float, p)), False) >= 0 for p in candidate):
            points = candidate
            break
    else:
        raise ValueError('PCB outline has no safe distributed reference frame; correct it manually.')
    _points(points, np.asarray(image), 'automatic reference')
    features = reference_features(image, polygon)
    if len(features['xy']) < 35:
        raise ValueError('Insufficient on-board detail; correct reference or retake a sharper photo.')
    return dict(points=points.tolist(), board_polygon=polygon, confirmed=True,
                source='automatic_board_corners', landmark_kind='board_coordinate_frame',
                coordinate_system='decoded_original_image_pixels',
                feature_count=len(features['xy']))


def reference_features(image, polygon):
    rgb = np.asarray(image)
    mask = surface_mask(rgb, polygon)
    scale = min(1., 1200/max(rgb.shape[:2]))
    gray = cv2.cvtColor(cv2.resize(rgb, None, fx=scale, fy=scale), cv2.COLOR_RGB2GRAY)
    small_mask = cv2.resize(mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    keys, descriptors = cv2.SIFT_create(nfeatures=3500, contrastThreshold=.025).detectAndCompute(gray, small_mask)
    # SIFT's mask checks only keypoint centers; reject descriptors whose support reaches off-board.
    distance = cv2.distanceTransform(small_mask, cv2.DIST_L2, 5)
    keep = [i for i, k in enumerate(keys) if distance[round(k.pt[1]), round(k.pt[0])] >= 5.5*k.size]
    xy = np.float32([keys[i].pt for i in keep]).reshape(-1, 2)/scale
    descriptors = descriptors[keep] if descriptors is not None and keep else None
    return dict(xy=xy, descriptors=descriptors, mask=mask, polygon=polygon)


def match_surfaces(features, inspection):
    try:
        other = reference_features(inspection, board_polygon(inspection))
    except ValueError as error:
        raise ValueError('Inspection PCB surface could not be isolated; use manual alignment or retake the photo.') from error
    a, b = features['descriptors'], other['descriptors']
    if a is None or b is None or min(len(a), len(b)) < 25:
        raise ValueError('Insufficient on-board features; use manual alignment or a sharper photo.')
    matcher = cv2.BFMatcher()
    forward = [p[0] for p in matcher.knnMatch(a, b, k=2) if len(p) == 2 and p[0].distance < .72*p[1].distance]
    reverse = {p[0].queryIdx: p[0].trainIdx for p in matcher.knnMatch(b, a, k=2)
               if len(p) == 2 and p[0].distance < .72*p[1].distance}
    matches, seen_a, seen_b = [], set(), set()
    for m in sorted(forward, key=lambda m: m.distance):
        x = tuple(np.round(features['xy'][m.queryIdx], 1))
        y = tuple(np.round(other['xy'][m.trainIdx], 1))
        if reverse.get(m.trainIdx) == m.queryIdx and x not in seen_a and y not in seen_b:
            matches.append(m)
            seen_a.add(x)
            seen_b.add(y)
    if len(matches) < 35:
        raise ValueError('Insufficient unique reciprocal on-board matches; manual alignment required. Check both images show the same PCB layout and board side.')
    return (np.float64([features['xy'][m.queryIdx] for m in matches]),
            np.float64([other['xy'][m.trainIdx] for m in matches]), other)


def verify_alignment(reference, inspection, features, matches, homography, aligned, valid):
    ref_xy, inspection_xy, other = matches
    recovered = cv2.perspectiveTransform(inspection_xy[None], homography)[0]
    error = np.linalg.norm(recovered-ref_xy, axis=1)
    limit = max(3., .003*np.hypot(*np.asarray(reference).shape[:2]))
    good = error <= limit
    # Every third correspondence is held out of homography fitting.
    holdout = np.arange(len(error)) % 3 == 0
    if good.sum() < 25 or good.mean() < .45 or (good & holdout).sum() < 8 or good[holdout].mean() < .45:
        raise ValueError('Distributed on-board reprojection check failed (including held-out matches).')
    mask = features['mask']
    hull = cv2.contourArea(cv2.convexHull(np.float32(ref_xy[good])))
    if hull/max(1, cv2.countNonZero(mask)) < .2:
        raise ValueError('Matches are concentrated in too small a part of the PCB.')
    ys, xs = np.nonzero(mask)
    bounds = (xs.min(), ys.min(), xs.max()+1, ys.max()+1)
    x1, y1, x2, y2 = bounds
    cells = set(zip(np.minimum(2, ((ref_xy[good, 0]-x1)*3/(x2-x1)).astype(int)),
                    np.minimum(2, ((ref_xy[good, 1]-y1)*3/(y2-y1)).astype(int))))
    if len(cells) < 6 or len({x for x, y in cells}) < 2 or len({y for x, y in cells}) < 2:
        raise ValueError('On-board matches do not cover enough separated PCB regions.')
    warped_surface = cv2.warpPerspective(other['mask'], homography, (mask.shape[1], mask.shape[0]))
    support = (mask > 0) & (warped_surface >= 254) & (valid == 255)
    overlap = support.sum()/max(1, cv2.countNonZero(mask))
    if overlap < .85:
        raise ValueError('Insufficient visible PCB overlap; board may be clipped or misaligned.')
    scores = []
    for row in range(3):
        for col in range(3):
            left, right = np.linspace(x1, x2, 4).astype(int)[col:col+2]
            top, bottom = np.linspace(y1, y2, 4).astype(int)[row:row+2]
            local = support[top:bottom, left:right]
            if local.mean() < .8:
                continue
            # Masked NCC of stable edges is independent of the four fitted landmarks.
            def edges(image):
                gray = cv2.cvtColor(np.asarray(image)[top:bottom, left:right], cv2.COLOR_RGB2GRAY)
                return cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0), cv2.Sobel(gray, cv2.CV_32F, 0, 1))[local]
            a, b = edges(reference), edges(aligned)
            score = float(np.corrcoef(a, b)[0, 1]) if min(a.std(), b.std()) > 1 else 0.
            scores.append(dict(row=row, column=col, score=score, matches=score >= .35))
    stable = [s for s in scores if s['matches']]
    if len(stable) < 5 or len({s['row'] for s in stable}) < 2 or len({s['column'] for s in stable}) < 2:
        raise ValueError('Stable PCB details disagree after alignment; manual review required.')
    return dict(method='reciprocal on-board SIFT; held-out reprojection and stable edge regions',
                matches=len(error), inliers=int(good.sum()), held_out_inliers=int((good & holdout).sum()),
                median_error_px=float(np.median(error[good])), p90_error_px=float(np.percentile(error[good], 90)),
                tolerance_px=limit, spatial_coverage=float(hull/cv2.countNonZero(mask)),
                occupied_cells=len(cells), board_overlap=float(overlap), stable_regions=scores)


def register_inspection(reference, inspection, points, features, detection, matches=None):
    rp = _points(points, np.asarray(reference), 'confirmed reference')
    matches = match_surfaces(features, inspection) if matches is None else matches
    attempts = []
    if detection['status'] == 'ok':
        ip = np.float64([[p['x'], p['y']] for p in detection['landmarks']])
        try:
            _points(ip, np.asarray(inspection), 'inspection YOLO landmarks')
            candidates = []
            # A rotated image can cyclically shift pose identities. Select the
            # same physical correspondence using independent on-board matches.
            for shift in range(4):
                ordered = np.roll(ip, -shift, axis=0)
                candidate = cv2.getPerspectiveTransform(np.float32(ordered), np.float32(rp))
                errors = np.linalg.norm(cv2.perspectiveTransform(matches[1][None], candidate)[0]-matches[0], axis=1)
                candidates.append((float(np.median(errors)), shift, ordered))
            error, shift, ip = min(candidates, key=lambda row: row[0])
            if error > max(3., .003*np.hypot(*np.asarray(reference).shape[:2])):
                raise ValueError('YOLO landmark transform disagrees with on-board matches.')
            aligned, matrix, valid = align_images(reference, inspection, rp, ip)
            evidence = verify_alignment(reference, inspection, features, matches, matrix, aligned, valid)
            return aligned, matrix, valid, dict(source='yolo_landmarks', inspection_points=ip.tolist(),
                                                inspection_landmark_order=[(i+shift) % 4 for i in range(4)],
                                                verification=evidence, attempts=attempts)
        except (ValueError, cv2.error, np.linalg.LinAlgError) as error:
            attempts.append(dict(source='yolo_landmarks', status='failure', reason=str(error)))
    else:
        attempts.append(dict(source='yolo_landmarks', status='failure', reason=detection['reason']))
    ref_xy, inspection_xy, _ = matches
    training = np.arange(len(ref_xy)) % 3 != 0
    matrix, _ = cv2.findHomography(inspection_xy[training], ref_xy[training], cv2.RANSAC,
                                   max(3., .003*np.hypot(*np.asarray(reference).shape[:2])))
    if matrix is None or not np.isfinite(matrix).all():
        raise ValueError('No robust on-board homography; use manual alignment.')
    try:
        ip = cv2.perspectiveTransform(rp[None], np.linalg.inv(matrix))[0]
    except np.linalg.LinAlgError as error:
        raise ValueError('Singular reference transform; use manual alignment.') from error
    # Reuse the existing geometry, horizon and bilinear-support validation.
    aligned, matrix, valid = align_images(reference, inspection, rp, ip)
    evidence = verify_alignment(reference, inspection, features, matches, matrix, aligned, valid)
    return aligned, matrix, valid, dict(source='reference_registration', inspection_points=ip.tolist(),
                                        landmark_kind='projected', verification=evidence, attempts=attempts)


def refine_manual_registration(reference, inspection, reference_points, inspection_points, features, matrix):
    """Refine small click errors only when independent board evidence improves."""
    matches = match_surfaces(features, inspection)
    before = np.linalg.norm(cv2.perspectiveTransform(matches[1][None], matrix)[0]-matches[0], axis=1)
    if np.median(before) <= .75:
        return None
    candidate = register_inspection(reference, inspection, reference_points, features,
        dict(status='failure', reason='Refining manual click residuals'), matches=matches)
    aligned, refined, valid, details = candidate
    correction = np.linalg.norm(np.asarray(details['inspection_points'])-inspection_points, axis=1).max()
    if (correction > max(3., .015*np.hypot(*np.asarray(inspection).shape[:2])) or
            details['verification']['p90_error_px'] >= .5*np.median(before)):
        return None
    details.update(source='manual_landmarks_refined', landmark_kind='manual_refined',
        manual_inspection_points=np.asarray(inspection_points).tolist(),
        manual_median_error_px=float(np.median(before)), max_click_correction_px=float(correction))
    return aligned, refined, valid, details
