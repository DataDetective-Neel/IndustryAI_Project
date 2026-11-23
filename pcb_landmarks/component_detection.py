"""Conservative classical-CV component proposals for golden PCB annotation."""
from __future__ import annotations

from pathlib import Path

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


def import_component_map(mapping, image_size, reference_filename):
    """Validate Antigravity's reference-only xywh map and convert to half-open xyxy."""
    if not isinstance(mapping, dict) or not isinstance(mapping.get("metadata"), dict):
        raise ValueError("Component map metadata is required")
    metadata = mapping["metadata"]
    dimensions = metadata.get("image_dimensions")
    expected_dimensions = {"width": image_size[0], "height": image_size[1]}
    if (not isinstance(dimensions, dict) or
            any(dimensions.get(key) != value for key, value in expected_dimensions.items())):
        raise ValueError("Component map dimensions must match the decoded golden image")
    mapped_name = metadata.get("reference_image_id")
    if not isinstance(mapped_name, str) or Path(mapped_name).name.lower() != Path(reference_filename).name.lower():
        raise ValueError("Component map reference image must match the uploaded golden image filename")
    source = mapping.get("components")
    if not isinstance(source, list) or not source or len(source) > 100:
        raise ValueError("Component map must contain 1 to 100 reference components")
    width, height = image_size
    converted, identifiers = [], set()
    for item in source:
        identifier, box = item.get("id") if isinstance(item, dict) else None, item.get("bbox") if isinstance(item, dict) else None
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError("Component map ids must be unique nonempty strings")
        if (not isinstance(box, list) or len(box) != 4 or
                any(type(value) is not int for value in box)):
            raise ValueError("Antigravity component bbox coordinates must be integer xywh values")
        x, y, box_width, box_height = box
        if box_width < 5 or box_height < 5 or x < 0 or y < 0 or x + box_width > width or y + box_height > height:
            raise ValueError("Component map xywh box is outside the decoded golden image")
        description = item.get("description", "")
        name = identifier.strip() if not isinstance(description, str) or not description.strip() else f"{identifier.strip()} — {description.strip()}"
        converted.append({"id": identifier.strip(), "name": name[:120],
                          "bbox_xyxy_px": [x, y, x + box_width, y + box_height]})
        identifiers.add(identifier)
    return converted


def propose_components(image, polygon=None, max_candidates=1000, reference_components=None):
    """Localize actual components with the pretrained ParsaVictor YOLO26 locator."""
    from .component_model import detect_components
    rgb = np.asarray(image.convert("RGB")) if hasattr(image, "convert") else np.asarray(image)
    if rgb.ndim != 3 or min(rgb.shape[:2]) < 80:
        raise ValueError("Golden image must be a color image at least 80x80 pixels")
    polygon = polygon or board_polygon(image)
    surface_mask(image, polygon)
    if reference_components:
        components = [dict(part, candidate_status="UNKNOWN",
                           proposal_evidence=dict(source="reference_component_map")) for part in reference_components]
        method = "Validated golden component map"
    else:
        components = detect_components(rgb, polygon, max_candidates)
        method = "ParsaVictor pretrained YOLO26 locator; native-resolution tiles and global NMS"
    return dict(board_polygon=polygon, components=components, candidate_count=len(components),
                method=method, verified=False)
