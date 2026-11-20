"""Original synthetic PCB-like pair; safe to publish, no source photographs."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def perspective_pair():
    reference = np.full((240, 320, 3), (25, 95, 55), dtype=np.uint8)
    for x in range(20, 310, 25):
        cv2.line(reference, (x, 15), (x, 225), (80, 150, 95), 1)
    for x, y in [(80, 65), (160, 120), (255, 180), (75, 195), (240, 55)]:
        cv2.rectangle(reference, (x-10, y-7), (x+10, y+7), (190, 185, 175), -1)
        cv2.line(reference, (x-13, y), (x+13, y), (10, 10, 10), 2)
    points = np.array([[35, 30], [285, 30], [285, 210], [35, 210]], dtype=float)
    forward = np.array([[.92, .12, -18], [-.08, 1.08, 18], [.0005, -.0004, 1]])
    inspection = cv2.warpPerspective(reference, forward, (300, 280))
    inspection_points = cv2.perspectiveTransform(points[None], forward)[0]
    controls = np.array([[80, 65], [160, 120], [255, 180], [75, 195], [240, 55]], dtype=float)
    return reference, inspection, points, inspection_points, forward, controls


def save_pair(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reference, inspection, rp, ip, forward, controls = perspective_pair()
    for name, image, points in [('reference', reference, rp), ('inspection', inspection, ip)]:
        Image.fromarray(image).save(output / f'{name}.png')
        normalized = points / [image.shape[1], image.shape[0]]
        triples = np.column_stack((normalized, np.full(4, 2))).ravel()
        (output / f'{name}.txt').write_text('0 0.5 0.5 1 1 ' +
                                          ' '.join(f'{v:.12g}' for v in triples) + '\n')
    (output / 'truth.json').write_text(json.dumps(dict(
        reference_to_inspection=forward.tolist(), reference_control_points=controls.tolist()), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    save_pair(parser.parse_args().output)
