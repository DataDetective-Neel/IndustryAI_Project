"""Original synthetic removal, present control and coverage case; no real photos."""
import argparse
import json
from pathlib import Path

import cv2
from PIL import Image

from alignment_fixture import perspective_pair, save_pair


def comparison_pair():
    reference, _, rp, ip, forward, _ = perspective_pair()
    removed = reference.copy()
    removed[110:131, 147:174] = (25, 95, 55)
    cv2.line(removed, (170, 110), (170, 130), (80, 150, 95), 1)
    inspection = cv2.warpPerspective(removed, forward, (300, 280))
    regions = dict(reference_image='reference.png', reference_wh_px=[320, 240], components=[
        dict(id='present', name='Present synthetic chip', bbox_xyxy_px=[60, 45, 100, 85]),
        dict(id='removed', name='Removed synthetic chip', bbox_xyxy_px=[140, 100, 180, 140]),
        dict(id='coverage', name='Synthetic coverage control', bbox_xyxy_px=[0, 50, 24, 90])])
    return reference, inspection, rp, ip, regions


def save_example(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    save_pair(output / 'input')
    _, inspection, _, _, regions = comparison_pair()
    Image.fromarray(inspection).save(output / 'input/inspection.png')
    (output / 'regions.json').write_text(json.dumps(regions, indent=2) + '\n')
    (output / 'ground_truth.json').write_text(json.dumps(dict(
        synthetic=True, description='Erased chip, restored textured traces before perspective warp',
        expected=dict(present='present', removed='uncertain', coverage='uncertain')), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    save_example(parser.parse_args().output)
