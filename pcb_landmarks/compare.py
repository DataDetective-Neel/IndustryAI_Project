"""Compare expected PCB regions in Step 4 reference coordinates (pilot thresholds)."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .align import blend_overlay
from .data import read_image


DISPLAY = dict(present='Present', missing='Missing', misaligned='Misaligned',
               uncertain='Needs review', not_evaluated='Not evaluated')


def _validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('Comparison configuration must be an object')
    values = [config.get(key) for key in ['missing_max', 'present_min']]
    if any(type(v) not in (int, float) or not np.isfinite(v) for v in values):
        raise ValueError('Score thresholds must be finite numbers')
    if not -1 <= values[0] < values[1] <= 1:
        raise ValueError('Require -1 <= missing_max < present_min <= 1')


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    _validate_config(config)
    return config


def _validate_regions(regions, size):
    if not isinstance(regions, dict) or regions.get('reference_wh_px') != list(size):
        raise ValueError('Region reference_wh_px must match the actual decoded reference')
    parts = regions.get('components')
    if not isinstance(parts, list) or not parts:
        raise ValueError('Expected a nonempty components list')
    for part in parts:
        if not isinstance(part, dict) or any(not isinstance(part.get(k), str) or not part[k].strip()
                                             for k in ['id', 'name']):
            raise ValueError('Each component needs a nonempty id and name')
        if 'review_reason' in part and (not isinstance(part['review_reason'], str) or not part['review_reason'].strip()):
            raise ValueError('review_reason must be nonempty text when supplied')
    if any(len({p[k] for p in parts}) != len(parts) for k in ['id', 'name']):
        raise ValueError('Component ids and names must be unique')
    return parts


def _box(box, width, height):
    return (isinstance(box, list) and len(box) == 4 and all(type(v) is int for v in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height
            and box[2]-box[0] >= 5 and box[3]-box[1] >= 5)


def _features(gray):
    return cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3),
                         cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))[1:-1, 1:-1]


def _score(reference, inspection, sharpen):
    features = []
    for name, crop in [('reference', reference), ('inspection', inspection)]:
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gradient = _features(gray)
        if gray.std() < 2 or gradient.std() < 1:
            return None, f'low_texture_{name}: raw grayscale/gradient variation is insufficient'
        if sharpen:
            gray = np.clip(gray + .5 * (gray - cv2.GaussianBlur(gray, (7, 7), 1)), 0, 255)
            gradient = _features(gray)
        if not np.isfinite(gradient).all() or gradient.std() < 1:
            return None, f'uninterpretable_{name}_gradient'
        features.append(gradient)
    score = float(cv2.matchTemplate(features[0], features[1], cv2.TM_CCOEFF_NORMED)[0, 0])
    if not np.isfinite(score) or not -1.000001 <= score <= 1.000001:
        return None, 'uninterpretable_correlation'
    return float(np.clip(score, -1, 1)), None


def _local_match(reference, aligned, mask, box, sharpen, search_radius=None, convincing_min=.5):
    x1, y1, x2, y2 = box
    # Search within the expected footprint neighborhood, independently of board registration.
    radius = search_radius if search_radius is not None else min(24, max(2, int(min(x2-x1, y2-y1)*.3)))
    height, width = mask.shape
    left, top = max(0, x1-radius), max(0, y1-radius)
    right, bottom = min(width, x2+radius), min(height, y2+radius)
    template = reference[y1:y2, x1:x2]
    _, reason = _score(template, template, sharpen)
    if reason:
        return dict(score=None, reason=reason, best_match_offset_px=None, search_radius_px=radius)
    a = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY).astype(np.float32)
    b = cv2.cvtColor(aligned[top:bottom, left:right], cv2.COLOR_RGB2GRAY).astype(np.float32)
    if sharpen:
        a = np.clip(a + .5*(a-cv2.GaussianBlur(a,(7,7),1)),0,255)
        b = np.clip(b + .5*(b-cv2.GaussianBlur(b,(7,7),1)),0,255)
    coverage = cv2.matchTemplate((mask[top:bottom,left:right] == 255).astype(np.float32),
                                 np.ones((y2-y1,x2-x1),np.float32), cv2.TM_CCORR)
    def locate(candidate):
        scores = cv2.matchTemplate(_features(b), _features(candidate), cv2.TM_CCOEFF_NORMED)
        scores[coverage < (y2-y1)*(x2-x1)-.5] = -2
        _, maximum, _, location = cv2.minMaxLoc(scores)
        return float(maximum), location

    zero_score, zero_location = locate(a)
    best_angle, maximum, (dx, dy) = 0.0, zero_score, zero_location
    center = ((a.shape[1]-1)/2, (a.shape[0]-1)/2)
    for angle in range(-30, 31, 3):
        if angle == 0:
            continue
        rotated = cv2.warpAffine(a, cv2.getRotationMatrix2D(center, angle, 1),
                                 (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REFLECT)
        candidate_score, location = locate(rotated)
        if candidate_score > maximum:
            maximum, (dx, dy), best_angle = candidate_score, location, float(angle)
    rotation_gain = maximum - zero_score
    if best_angle and rotation_gain < .08:
        best_angle, maximum, (dx, dy) = 0.0, zero_score, zero_location
    if maximum < -1:
        return dict(score=None,reason='insufficient_search_coverage',best_match_offset_px=None,search_radius_px=radius)
    bx, by = left+dx, top+dy
    matched = aligned[by:by+y2-y1,bx:bx+x2-x1]
    comparison_template = template
    if best_angle:
        comparison_template = cv2.warpAffine(template, cv2.getRotationMatrix2D(center, best_angle, 1),
                                             (template.shape[1], template.shape[0]), flags=cv2.INTER_LINEAR,
                                             borderMode=cv2.BORDER_REFLECT)
    score, reason = _score(comparison_template, matched, sharpen)
    narrow_radius = min(6, max(1, int(min(x2-x1, y2-y1)*.08)))
    if search_radius is None and radius > narrow_radius and (score is None or score < convincing_min):
        # Nearby traces cannot substitute for an absent component. Keep the
        # original footprint evidence unless relocation has a convincing match.
        local = _local_match(reference, aligned, mask, box, sharpen, narrow_radius, convincing_min)
        local.setdefault('evidence', {})['rejected_wide_search_score'] = score
        return local
    ref_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY).astype(np.float32)
    current_gray = cv2.cvtColor(matched, cv2.COLOR_RGB2GRAY).astype(np.float32)
    ref_energy, current_energy = float(_features(ref_gray).mean()), float(_features(current_gray).mean())
    edge_ratio = current_energy/ref_energy if ref_energy > 1e-6 else None
    color_delta = float(np.abs(cv2.cvtColor(template, cv2.COLOR_RGB2LAB).astype(np.float32) -
                               cv2.cvtColor(matched, cv2.COLOR_RGB2LAB).astype(np.float32)).mean()/255)
    offset = [bx-x1, by-y1]
    # A missing body can leave sharply defined solder pads. Measure the loss of
    # its neutral surface into the colored substrate independently of pad edges.
    padding = max(3, round(min(x2-x1, y2-y1)*.2))
    neighborhood = reference[max(0,y1-padding):min(height,y2+padding), max(0,x1-padding):min(width,x2+padding)]
    board_saturation = float(np.percentile(cv2.cvtColor(neighborhood, cv2.COLOR_RGB2HSV)[:,:,1], 80))
    ref_saturation = cv2.cvtColor(template, cv2.COLOR_RGB2HSV)[:,:,1]
    current_saturation = cv2.cvtColor(aligned[y1:y2,x1:x2], cv2.COLOR_RGB2HSV)[:,:,1]
    body = ref_saturation < .5*board_saturation
    body_ratio = replacement = None
    rule_body_ratio = rule_replacement = None
    if board_saturation >= 100 and body.mean() >= .2:
        rule_body_ratio = float((current_saturation[body] < .5*board_saturation).mean())
        rule_replacement = float((current_saturation[body] > .7*board_saturation).mean())
    if board_saturation >= 100 and body.mean() >= .6:
        body_ratio = float((current_saturation[body] < .5*board_saturation).mean())
        replacement = float((current_saturation[body] > .7*board_saturation).mean())
    return dict(score=score, reason=reason, best_match_offset_px=offset, search_radius_px=radius,
                evidence=dict(edge_energy_ratio=edge_ratio, mean_lab_delta=color_delta,
                              remaining_body_ratio=body_ratio, substrate_replacement_ratio=replacement,
                              absence_body_remaining=rule_body_ratio, absence_substrate_replacement=rule_replacement,
                              reference_edge_energy=ref_energy, inspection_edge_energy=current_energy,
                              rotation_deg=best_angle, rotation_score_gain=float(rotation_gain),
                              displacement_px=offset,
                              displacement_magnitude_px=float(np.linalg.norm(offset))))


def _overlay_score(reference, aligned, mask):
    height, width = mask.shape
    size = (max(3,round(width*min(1,320/max(width,height)))),
            max(3,round(height*min(1,320/max(width,height)))))
    a,b = [cv2.resize(im,size,interpolation=cv2.INTER_AREA) for im in (reference,aligned)]
    valid = cv2.erode(cv2.resize(mask,size,interpolation=cv2.INTER_NEAREST),np.ones((5,5),np.uint8))[1:-1,1:-1] == 255
    a,b = [_features(cv2.cvtColor(im,cv2.COLOR_RGB2GRAY).astype(np.float32))[valid] for im in (a,b)]
    if len(a) < 100 or min(a.std(),b.std()) < 1:
        return None
    return float(np.corrcoef(a,b)[0,1])


def compare_regions(reference, aligned, mask, regions, config, alignment, sharpen=False, detection_evidence=None):
    """Return region findings; invalid crops/coverage are uncertain, failed alignment skips all.

    Arrays are decoded RGB uint8; mask is Step 4 single-channel uint8 0/255.
    Pixel rectangles are half-open. The Step 4 status/dimensions are required;
    an ok warp is a prerequisite, not a global or local quality certification.
    """
    _validate_config(config)
    reference = np.asarray(reference)
    if reference.ndim != 3 or reference.shape[2] != 3 or reference.dtype != np.uint8 or not reference.size:
        raise ValueError('Expected a nonempty decoded RGB uint8 reference')
    height, width = reference.shape[:2]
    parts = _validate_regions(regions, (width, height))
    if not isinstance(alignment, dict) or alignment.get('status') not in ['ok', 'failure']:
        raise ValueError('Expected Step 4 alignment status ok or failure')
    failed = alignment['status'] == 'failure'
    if not failed:
        aligned, mask = np.asarray(aligned), np.asarray(mask)
        if aligned.shape != reference.shape or aligned.dtype != np.uint8:
            raise ValueError('Aligned inspection must be RGB uint8 in the reference pixel grid')
        if mask.shape != (height, width) or mask.dtype != np.uint8 or not np.isin(mask, [0, 255]).all():
            raise ValueError('Overlap mask must be single-channel uint8 0/255 in the reference pixel grid')
        if alignment.get('reference_wh') != [width, height]:
            raise ValueError('Alignment metadata dimensions do not match the reference')
    result = dict(status='failure' if failed else 'ok', outcome='review' if failed else None,
                  reason=(alignment.get('reason') or 'alignment_failed') if failed else None,
                  review_required=failed, reference_wh_px=[width, height],
                  coordinate_system='decoded_reference_pixels', thresholds_provisional=True,
                  config=dict(config), sharpening_enabled=sharpen,
                  absence_policy='Missing requires low correlation, lost edges or corroborated body loss into substrate, and appearance change; thresholds are provisional',
                  method=dict(feature='Sobel magnitude ksize=3, trim 1px border', correlation='TM_CCOEFF_NORMED',
                              search='bounded local gradient template match, <=24px translation and -30..30 degree rotation hypotheses', min_coverage=1.0, min_crop_side_px=5, min_raw_gray_std=2, min_gradient_std=1,
                              unsharp=dict(amount=.5, sigma=1, kernel=[7, 7])), components=[], overlay=None)
    for part in parts:
        box = part.get('bbox_xyxy_px')
        valid = _box(box, width, height)
        row = dict(id=part['id'], name=part['name'], bbox_xyxy_px=box if valid else None,
                   overlap=None, score=None, status='not_evaluated' if failed else 'uncertain', reason=None)
        if failed:
            row['reason'] = result['reason']
        elif not valid:
            row['reason'] = 'invalid_crop: require integer in-bounds xyxy and minimum 5x5 pixels'
        else:
            x1, y1, x2, y2 = box
            row['overlap'] = float(np.mean(mask[y1:y2, x1:x2] == 255))
            if row['overlap'] < 1:
                row['reason'] = 'insufficient_coverage: full region coverage is required'
            elif part.get('review_reason'):
                row['reason'] = 'explicit_review: ' + part['review_reason']
            else:
                row.update(_local_match(reference, aligned, mask, box, sharpen,
                                        convincing_min=config['present_min']))
                if row['score'] is not None:
                    rotation = abs(row.get('evidence', {}).get('rotation_deg', 0))
                    if rotation >= config.get('misalignment_rotation_min_deg', 8) and row['score'] >= config['present_min']:
                        row.update(status='misaligned', reason='component_rotation_after_board_registration')
                    elif row['score'] >= config['present_min']:
                        row.update(status='present', reason='convincing_bounded_local_match')
                    elif (row['score'] <= config['missing_max'] and
                          row.get('evidence', {}).get('edge_energy_ratio') is not None and
                          (row['evidence']['edge_energy_ratio'] <= config.get('missing_edge_ratio_max', .45) or
                           (row['evidence'].get('remaining_body_ratio') is not None and
                            alignment.get('verification', {}).get('p90_error_px', float('inf')) <= max(1., .02*min(x2-x1,y2-y1)) and
                            row['evidence']['remaining_body_ratio'] <= config.get('missing_body_ratio_max', .55) and
                            row['evidence']['substrate_replacement_ratio'] >= config.get('missing_substrate_ratio_min', .35))) and
                          row['evidence']['mean_lab_delta'] >= config.get('missing_color_delta_min', .03)):
                        row.update(status='missing', reason='corroborated_absence: low structural match, lost edges or component body, and changed appearance')
                    else:
                        row['reason'] = 'ambiguous_appearance: low similarity alone cannot establish absence'
        row['display_status'] = DISPLAY[row['status']]
        result['components'].append(row)
    if not failed:
        overlay_score = _overlay_score(reference, aligned, mask)
        present = [p for p in result['components'] if p['status'] == 'present']
        offsets = [p['best_match_offset_px'] for p in present]
        consistent = len(offsets) >= max(2, int(np.ceil(.6*len(parts)))) and np.ptp(np.array(offsets),axis=0).max() <= 3
        reliable = ((overlay_score is not None and overlay_score >= .35) or consistent) and (mask == 255).mean() >= .6
        result['alignment_validation'] = dict(reliable=bool(reliable), overlay_score=overlay_score,
                                              reason='overlay_or_consistent_local_matches' if reliable else 'unreliable_overlay_or_coverage')
        if not reliable:
            for row in result['components']:
                row.update(status='uncertain',display_status=DISPLAY['uncertain'],reason='unreliable_alignment: overlay/coverage validation failed; ' + (row['reason'] or 'no_local_match'))
        else:
            matched = [row for row in result['components'] if row['status'] == 'present' and row.get('best_match_offset_px')]
            if len(matched) >= 2 or alignment.get('verification_status') == 'verified':
                global_offset = np.zeros(2)
                if len(matched) >= 3:
                    offsets = np.asarray([row['best_match_offset_px'] for row in matched])
                    median = np.median(offsets, axis=0)
                    if (np.linalg.norm(offsets-median, axis=1) <= 3).mean() >= .6:
                        global_offset = median
                for row in matched:
                    deviation = float(np.linalg.norm(np.asarray(row['best_match_offset_px']) - global_offset))
                    x1, y1, x2, y2 = row['bbox_xyxy_px']
                    size = min(x2-x1, y2-y1)
                    residual = alignment.get('verification', {}).get('p90_error_px', 0)
                    tolerance = max(config.get('misalignment_min_px', 2.5),
                                    size*config.get('misalignment_dimension_fraction', .05),
                                    2*residual+1 if residual else 0)
                    row.setdefault('evidence', {}).update(offset_deviation_px=deviation,
                        normalized_displacement=deviation/size, displacement_tolerance_px=float(tolerance),
                        registration_residual_px=float(residual), consensus_offset_px=global_offset.tolist())
                    if deviation > tolerance:
                        row.update(status='misaligned', display_status=DISPLAY['misaligned'],
                                   reason='individual_offset_differs_from_consensus_after_board_registration')
        states = {p['status'] for p in result['components']}
        defects = states & {'missing', 'misaligned'}
        result['review_required'] = bool('uncertain' in states or defects)
        result['outcome'] = 'defect' if defects else 'review' if result['review_required'] else 'ok'
    if detection_evidence is not None:
        from .correspondence import assign_components
        valid_parts = [p for p in parts if _box(p.get('bbox_xyxy_px'), width, height)]
        reference_matches = assign_components(valid_parts, detection_evidence.get('reference', {}).get('components', []))
        # Manual boxes remain authoritative; borrow a detector class only when
        # its reference footprint substantially agrees with the corrected box.
        detected_reference = {p.get('id'): p for p in detection_evidence.get('reference', {}).get('components', [])}
        typed_parts = []
        for part in valid_parts:
            match = reference_matches.get(part['id'])
            source = detected_reference.get(match['observed_id']) if match and match['iou'] >= .5 else None
            typed_parts.append(dict(part, proposal_evidence=source.get('proposal_evidence', {})) if source else part)
        inspection_matches = assign_components(typed_parts,
            detection_evidence.get('inspection', {}).get('components', []), np.asarray(reference), aligned if not failed else None)
        for row in result['components']:
            if not row.get('bbox_xyxy_px'):
                continue
            evidence = dict(reference=reference_matches.get(row['id']), inspection=inspection_matches.get(row['id']))
            row['detector_evidence'] = evidence
            observed = evidence['inspection']
            if observed is None and row['status'] in {'present', 'misaligned'} and inspection_matches:
                from .component_detection import _box_iou
                offset = row.get('best_match_offset_px')
                if offset and np.linalg.norm(offset) > config.get('misalignment_min_px', 2.5):
                    local_box = (np.asarray(row['bbox_xyxy_px']) + np.tile(offset, 2)).tolist()
                    if any(_box_iou(local_box, match['bbox_xyxy_px']) >= .5 for match in inspection_matches.values()):
                        row.update(status='uncertain', display_status=DISPLAY['uncertain'],
                                   reason='ambiguous_correspondence: local appearance points to a component already assigned elsewhere')
            # Exposed solder pads retain strong edges, so edge loss alone misses
            # removed bodies. Require independent body/substrate and color evidence,
            # verified registration, no nearby convincing match, and detector absence.
            measurements = row.get('evidence', {})
            if (row['status'] == 'uncertain'
                    and result.get('alignment_validation', {}).get('reliable')
                    and alignment.get('verification_status') == 'verified'
                    and row.get('overlap') == 1
                    and not next((p.get('review_reason') for p in parts if p['id'] == row['id']), None)
                    and observed is None and evidence['reference'] is not None
                    and row.get('score') is not None and row['score'] <= config['missing_max']
                    and measurements.get('rejected_wide_search_score', row['score']) is not None
                    and measurements.get('rejected_wide_search_score', row['score']) < config['present_min']
                    and measurements.get('absence_body_remaining') is not None
                    and measurements['absence_body_remaining'] <= .65
                    and measurements['absence_substrate_replacement'] >= .25
                    and measurements.get('mean_lab_delta', 0) >= .08):
                row.update(status='missing', display_status=DISPLAY['missing'],
                           reason='rule_based_absence: body replaced by substrate, changed color, no detected or nearby matching component')
            # A detection cannot establish presence by itself. Strong conflicting
            # evidence makes an absence decision reviewable rather than certain.
            if (row['status'] == 'missing' and observed and observed['iou'] >= .5
                    and (observed['confidence'] or 0) >= .65):
                row.update(status='uncertain', display_status=DISPLAY['uncertain'],
                           reason='conflicting_component_detection_and_absence_evidence')
        states = {p['status'] for p in result['components']}
        defects = states & {'missing','misaligned'}
        result['review_required'] = bool('uncertain' in states or defects or failed)
        result['outcome'] = 'defect' if defects else 'review' if result['review_required'] else 'ok'
    for row in result['components']:
        row['classification'] = dict(present='GOOD', missing='MISSING_COMPONENT',
                                     misaligned='MISALIGNED_COMPONENT').get(row['status'], 'NEEDS_REVIEW')
        row['decision'] = ('ROTATED' if row['status'] == 'misaligned' and
            abs(row.get('evidence', {}).get('rotation_deg', 0)) >= config.get('misalignment_rotation_min_deg', 8)
            else dict(present='PRESENT', missing='MISSING', misaligned='SHIFTED').get(row['status'], 'NEEDS_REVIEW'))
        row['expected_location'] = row.get('bbox_xyxy_px')
        row['observed_location'] = (row.get('detector_evidence', {}).get('inspection') or {}).get('bbox_xyxy_px')
    states = {row['classification'] for row in result['components']}
    result['classifications'] = sorted(states)
    return result


def annotated_overlay(reference, aligned, mask, report):
    # shortcut: labels suit sparse pilot regions, add wrapping/packing for dense boards.
    image = Image.fromarray(blend_overlay(np.asarray(reference), np.asarray(aligned), mask))
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=14)
    title = f"Pilot: {report['outcome']} | sharpening {'on' if report['sharpening_enabled'] else 'off'}"
    occupied = [draw.textbbox((3, 3), title, font=font)]
    draw.rectangle(occupied[0], fill='black')
    draw.text((3, 3), title, fill='white', font=font)
    colors = dict(present='#37cc77', missing='#ff5050', misaligned='#ff8c42', uncertain='#ffc247')
    for part in report['components']:
        box = part['bbox_xyxy_px']
        text = f"{part['name']}: {part['display_status']}"
        if box is None:
            text += ' (invalid box)'
            x, y = 3, max(b[3] for b in occupied) + 3
        else:
            x1, y1, x2, y2 = box
            draw.rectangle((x1, y1, x2-1, y2-1), outline=colors[part['status']], width=3)
            x, y = x1, max(22, y1-20)
        tw = draw.textbbox((0, 0), text, font=font)[2]
        x = max(0, min(x, image.width-tw-4))
        bounds = draw.textbbox((x+2, y), text, font=font)
        if box is not None and any(bounds[0] < b[2] and bounds[2] > b[0] and bounds[1] < b[3] and bounds[3] > b[1]
                                   for b in occupied):
            y = min(image.height-18, box[3]+2)
            bounds = draw.textbbox((x+2, y), text, font=font)
        occupied.append(bounds)
        draw.rectangle(bounds, fill='black')
        draw.text((x+2, y), text, fill=colors[part['status']], font=font)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--aligned', required=True)
    parser.add_argument('--mask', required=True)
    parser.add_argument('--regions', required=True)
    parser.add_argument('--config', default='configs/comparison.json')
    parser.add_argument('--alignment-report', help='Default: alignment.json beside the aligned image')
    parser.add_argument('--sharpen', action='store_true', help='Symmetric mild unsharp, default off')
    parser.add_argument('--output', required=True, help='New local output directory')
    args = parser.parse_args()
    output = Path(args.output)
    error_result = lambda error: dict(status='failure', outcome='error', reason=f'{type(error).__name__}: {error}',
                                      review_required=False, components=[], overlay=None)
    if output.exists():
        print(json.dumps(error_result(FileExistsError('Output directory must not exist')), indent=2))
        raise SystemExit(2)
    try:
        reference = read_image(args.reference)
        regions = json.loads(Path(args.regions).read_text(encoding='utf-8'))
        alignment_path = Path(args.alignment_report) if args.alignment_report else Path(args.aligned).parent/'alignment.json'
        alignment = json.loads(alignment_path.read_text(encoding='utf-8'))
        config = load_config(args.config)
        if (not isinstance(regions, dict) or not isinstance(regions.get('reference_image'), str)
                or Path(regions['reference_image']).name != Path(args.reference).name):
            raise ValueError('Region reference_image must name the supplied reference')
        aligned, mask = None, None
        if isinstance(alignment, dict) and alignment.get('status') == 'ok':
            if not isinstance(alignment.get('outputs'), dict):
                raise ValueError('Alignment metadata must record its output paths')
            for key, path in [('aligned', args.aligned), ('mask', args.mask)]:
                recorded = alignment['outputs'].get(key)
                if not isinstance(recorded, str) or Path(recorded).resolve() != Path(path).resolve():
                    raise ValueError(f'{key} path does not match Step 4 output metadata')
            aligned = read_image(args.aligned)
            with Image.open(args.mask) as image:
                if image.mode != 'L' or image.getexif().get(274, 1) != 1:
                    raise ValueError('Expected an orientation-normalized single-channel overlap mask')
                mask = np.array(image)
        result = compare_regions(reference, aligned, mask, regions, config, alignment, args.sharpen)
        result['inputs'] = {key: str(Path(path).resolve()) for key, path in
                            [('reference', args.reference), ('aligned', args.aligned), ('mask', args.mask),
                             ('regions', args.regions), ('alignment_report', alignment_path), ('config', args.config)]}
        overlay = annotated_overlay(reference, aligned, mask, result) if result['status'] == 'ok' else None
    except (OSError, ValueError, cv2.error) as error:
        result, overlay = error_result(error), None
    try:
        output.mkdir(parents=True, exist_ok=False)
        if overlay is not None:
            result['overlay'] = str((output/'overlay.png').resolve())
            overlay.save(output/'overlay.png')
        (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    except (OSError, ValueError) as error:
        result = error_result(error)
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if result['status'] == 'ok' else 2)


if __name__ == '__main__':
    main()
