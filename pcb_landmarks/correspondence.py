"""One-to-one component correspondence in the active reference pixel grid."""
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .component_detection import _box_iou


def transform_components(components, homography, reference_wh):
    """Transform original detections, retaining the quadrilateral and source box."""
    width, height = reference_wh
    transformed = []
    for component in components:
        x1, y1, x2, y2 = component['bbox_xyxy_px']
        corners = np.float64([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]])
        quad = cv2.perspectiveTransform(corners, np.asarray(homography, np.float64))[0]
        if not np.isfinite(quad).all():
            continue
        low = np.maximum(0, np.floor(quad.min(axis=0))).astype(int)
        high = np.minimum([width, height], np.ceil(quad.max(axis=0))).astype(int)
        if np.any(high-low < 5):
            continue
        transformed.append(dict(component, original_bbox_xyxy_px=[x1, y1, x2, y2],
            center_xy_px=((low+high)/2).tolist(), width_px=int(high[0]-low[0]), height_px=int(high[1]-low[1]),
            quadrilateral_reference_px=quad.tolist(), bbox_xyxy_px=[*low.tolist(), *high.tolist()]))
    return transformed


def assign_components(reference, observed, reference_image=None, aligned_image=None):
    """Hungarian assignment with unmatched options; detections alone do not prove presence.

    Gates allow nearby displacement up to one component diagonal and a 2x
    dimension ratio. These provisional gates constrain correspondence, not defects.
    """
    if not reference or not observed:
        return {}
    costs = np.full((len(reference), len(observed)+len(reference)), 1., np.float64)
    measurements = {}
    for i, expected in enumerate(reference):
        a = np.asarray(expected['bbox_xyxy_px'], float)
        size = a[2:]-a[:2]
        center = (a[:2]+a[2:])/2
        cls = expected.get('proposal_evidence', {}).get('class_id')
        for j, current in enumerate(observed):
            b = np.asarray(current['bbox_xyxy_px'], float)
            other_size = b[2:]-b[:2]
            other_cls = current.get('proposal_evidence', {}).get('class_id')
            delta = (b[:2]+b[2:])/2-center
            distance = float(np.linalg.norm(delta))
            ratio = other_size/size
            if (np.any(ratio < .5) or np.any(ratio > 2) or
                    distance > np.linalg.norm(size) or
                    (cls is not None and other_cls is not None and cls != other_cls)):
                costs[i, j] = 1000
                continue
            iou = _box_iou(a, b)
            appearance = None
            if reference_image is not None and aligned_image is not None:
                from .compare import _score
                x1, y1, x2, y2 = a.astype(int)
                u1, v1, u2, v2 = b.astype(int)
                crop = aligned_image[v1:v2, u1:u2]
                if crop.size:
                    appearance, _ = _score(reference_image[y1:y2, x1:x2],
                        cv2.resize(crop, (x2-x1, y2-y1)), False)
            cost = .5*distance/np.linalg.norm(size) + .3*(1-iou) + .1*float(np.abs(np.log(ratio)).sum())
            if appearance is not None:
                cost += .2*(1-appearance)/2
            costs[i, j] = cost
            measurements[i, j] = dict(observed_id=current.get('id'), bbox_xyxy_px=b.astype(int).tolist(),
                confidence=current.get('proposal_confidence'), iou=float(iou),
                displacement_vector_px=delta.tolist(), displacement_px=distance,
                normalized_displacement=distance/float(min(size)), appearance_score=appearance)
    rows, columns = linear_sum_assignment(costs)
    return {reference[i]['id']: measurements[i, j] for i, j in zip(rows, columns)
            if j < len(observed) and costs[i, j] < 1}
