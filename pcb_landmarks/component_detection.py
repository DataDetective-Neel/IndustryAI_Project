"""Conservative classical-CV component proposals for golden PCB annotation."""
from __future__ import annotations

import cv2
import numpy as np

from .registration import board_polygon, surface_mask


def _box_iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2-x1) * max(0, y2-y1)
    if not intersection:
        return 0.0
    return intersection / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection)


def _coverage(mask, box):
    x1, y1, x2, y2 = box
    return float((mask[y1:y2, x1:x2] > 0).mean())


def propose_components(image, polygon=None, max_candidates=36):
    """Return operator-review candidates; never claims verified component identity."""
    rgb = np.asarray(image.convert("RGB")) if hasattr(image, "convert") else np.asarray(image)
    if rgb.ndim != 3 or min(rgb.shape[:2]) < 80:
        raise ValueError("Golden image must be a color image at least 80x80 pixels")
    height, width = rgb.shape[:2]
    polygon = polygon or board_polygon(image)
    mask = surface_mask(image, polygon)
    board_area = max(1, int((mask > 0).sum()))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    normalized[mask == 0] = int(np.median(normalized[mask > 0]))

    median = float(np.median(normalized[mask > 0]))
    edges = cv2.Canny(normalized, max(20, int(.55*median)), min(220, int(1.35*median)))
    adaptive = cv2.adaptiveThreshold(normalized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, 31, 7)
    edge_map = cv2.bitwise_or(edges, cv2.morphologyEx(adaptive, cv2.MORPH_GRADIENT,
                                                      np.ones((3, 3), np.uint8)))
    edge_map[mask == 0] = 0

    scales = [
        cv2.morphologyEx(edge_map, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2),
        cv2.morphologyEx(edge_map, cv2.MORPH_CLOSE, np.ones((11, 7), np.uint8), iterations=2),
    ]
    candidates = []
    min_area, max_area = board_area * .00055, board_area * .075
    for scale_index, binary in enumerate(scales):
        if scale_index:
            binary = cv2.dilate(binary, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w*h
            box = [int(x), int(y), int(x+w), int(y+h)]
            if not min_area <= area <= max_area or min(w, h) < 18 or max(w/h, h/w) > 7:
                continue
            if _coverage(mask, box) < .82:
                continue
            contour_fill = cv2.contourArea(contour) / area
            edge_density = float((edges[y:y+h, x:x+w] > 0).mean())
            if contour_fill < .035 or edge_density < .012:
                continue
            pad = max(4, int(.08*max(w, h)))
            ox1, oy1, ox2, oy2 = max(0, x-pad), max(0, y-pad), min(width, x+w+pad), min(height, y+h+pad)
            outer = normalized[oy1:oy2, ox1:ox2]
            inner = normalized[y:y+h, x:x+w]
            contrast = abs(float(inner.mean()) - float(outer.mean())) / 255
            score = min(.94, .18 + 1.6*edge_density + .55*min(contour_fill, .7) + .5*contrast
                        + min(.22, 4*np.sqrt(area/board_area)))
            candidates.append(dict(box=box, score=score, edge_density=edge_density,
                                   contour_fill=float(contour_fill), contrast=contrast))

    # Dark, low-texture IC packages can have weak outer edges on a dark solder mask.
    # Multiple board-relative thresholds recover their rectangular bodies without
    # treating threshold membership as verified identity.
    board_values = gray[mask > 0]
    for threshold in np.unique(np.percentile(board_values, [45, 55, 65, 75]).astype(np.uint8)):
        dark = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY_INV)[1]
        dark[mask == 0] = 0
        contours, _ = cv2.findContours(dark, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w*h
            box = [int(x), int(y), int(x+w), int(y+h)]
            if not min_area <= area <= max_area or min(w, h) < 18 or max(w/h, h/w) > 6:
                continue
            if _coverage(mask, box) < .88:
                continue
            fill = cv2.contourArea(contour) / area
            if fill < .22:
                continue
            edge_density = float((edges[y:y+h, x:x+w] > 0).mean())
            inner = gray[y:y+h, x:x+w]
            contrast = max(0.0, (float(threshold) - float(inner.mean())) / 255)
            relative_area = area/board_area
            score = min(.98, .25 + .25*min(fill, 1) + .8*edge_density + .25*contrast
                        + .35*np.sqrt(min(1, relative_area/.02)))
            candidates.append(dict(box=box, score=score, edge_density=edge_density,
                                   contour_fill=float(fill), contrast=contrast))

    candidates.sort(key=lambda item: item["score"], reverse=True)
    def grid_cell(item):
        box = item["box"]
        return (min(5, int(6*((box[0]+box[2])/2)/width)),
                min(7, int(8*((box[1]+box[3])/2)/height)))

    # Reserve one proposal per occupied board cell before score-only filling.
    # This prevents dense silkscreen at one edge from consuming every slot.
    primary, occupied = [], set()
    for candidate in candidates:
        cell = grid_cell(candidate)
        if cell not in occupied:
            primary.append(candidate)
            occupied.add(cell)
    primary.sort(key=lambda item: (grid_cell(item)[1], grid_cell(item)[0]))
    ordered = primary + [candidate for candidate in candidates if candidate not in primary]
    selected = []
    grid_counts = {}
    for candidate in ordered:
        box = candidate["box"]
        cell = grid_cell(candidate)
        if grid_counts.get(cell, 0) >= 2:
            continue
        if any(_box_iou(box, other["box"]) > .32 or
               (box[0] >= other["box"][0] and box[1] >= other["box"][1] and
                box[2] <= other["box"][2] and box[3] <= other["box"][3])
               for other in selected):
            continue
        selected.append(candidate)
        grid_counts[cell] = grid_counts.get(cell, 0) + 1
        if len(selected) >= max_candidates:
            break

    selected.sort(key=lambda item: ((item["box"][1]+item["box"][3])//80,
                                    item["box"][0], item["box"][1]))
    components = []
    for index, item in enumerate(selected, 1):
        components.append({
            "id": f"AUTO-{index:03d}", "name": f"UNKNOWN {index:03d}",
            "bbox_xyxy_px": item["box"], "candidate_status": "UNKNOWN",
            "proposal_confidence": round(item["score"], 3),
            "proposal_evidence": {
                "edge_density": round(item["edge_density"], 4),
                "contour_fill": round(item["contour_fill"], 4),
                "local_contrast": round(item["contrast"], 4),
            },
        })
    return {"board_polygon": [[float(x), float(y)] for x, y in polygon],
            "components": components, "candidate_count": len(components),
            "method": "CLAHE, adaptive threshold, Canny edges, morphology, contour filtering and overlap suppression",
            "verified": False}
