"""Validation-only threshold selection, then frozen held-out landmark evaluation."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .data import DEFAULT_DATA, audit, read_image, read_label, resolved_yaml, split_records
from .infer import LandmarkDetector, assess


def box_iou(boxes, target):
    boxes = np.asarray(boxes).reshape(-1, 4)
    intersection = np.maximum(0, np.minimum(boxes[:, 2:], target[2:]) - np.maximum(boxes[:, :2], target[:2])).prod(1)
    area = np.maximum(0, boxes[:, 2:] - boxes[:, :2]).prod(1)
    target_area = np.maximum(0, target[2:] - target[:2]).prod()
    return intersection / np.maximum(area + target_area - intersection, 1e-9)


def summarize(records, names, board_conf, point_conf, tolerance_fraction):
    errors = [[] for _ in names]
    result = dict(images=len(records), matched_predictions=0, all_four_usable=0,
                  all_four_within_tolerance=0, confident_but_inaccurate=0,
                  failed_detections=0, rows=[])
    for row in records:
        detection = assess(row['boxes'], row['scores'], row['points'], names,
                           row['size'], board_conf, point_conf)
        usable = detection['status'] == 'ok'
        overlaps = box_iou(row['boxes'], row['gt_box'])
        eligible = np.flatnonzero((np.asarray(row['scores']) >= .001) & (overlaps >= .5))
        match = int(eligible[np.argmax(row['scores'][eligible])]) if len(eligible) else None
        matched = match is not None and overlaps[match] >= .5
        distances = None
        accurate = False
        tolerance = float(np.hypot(*row['size']) * tolerance_fraction)
        if matched and np.asarray(row['points'][match]).shape == (4, 3):
            points = np.asarray(row['points'][match])
            if np.isfinite(points).all():
                result['matched_predictions'] += 1
                distances = np.linalg.norm(points[:, :2] - row['gt_points'][:, :2], axis=1)
                for i in range(4):
                    if row['gt_points'][i, 2] > 0:
                        errors[i].append(float(distances[i]))
        if usable:
            accepted = np.array([[p['x'], p['y']] for p in detection['landmarks']])
            accepted_errors = np.linalg.norm(accepted - row['gt_points'][:, :2], axis=1)
            accurate = bool(box_iou([detection['bbox_xyxy']], row['gt_box'])[0] >= .5
                            and (row['gt_points'][:, 2] > 0).all()
                            and (accepted_errors <= tolerance).all())
        result['all_four_usable'] += int(usable)
        result['all_four_within_tolerance'] += int(usable and accurate)
        result['confident_but_inaccurate'] += int(usable and not accurate)
        result['failed_detections'] += int(not usable)
        result['rows'].append(dict(image=row['image'], status=detection['status'],
                                   reason=detection['reason'], matched=bool(matched),
                                   all_four_accurate=bool(usable and accurate), tolerance_px=tolerance,
                                   errors_px=distances.tolist() if distances is not None else None,
                                   detection=detection))
    result['per_landmark'] = {
        name: dict(count=len(values), mean_px=float(np.mean(values)) if values else None,
                   median_px=float(np.median(values)) if values else None,
                   p95_px=float(np.percentile(values, 95)) if values else None)
        for name, values in zip(names, errors)
    }
    return result


def select_thresholds(records, names, tolerance_fraction):
    candidates = []
    for board_conf in [.25, .5, .75, .9, .95]:
        for point_conf in [.5, .7, .85, .95, .99]:
            summary = summarize(records, names, board_conf, point_conf, tolerance_fraction)
            candidates.append(dict(board_conf=board_conf, point_conf=point_conf, summary=summary))
    # Prefer zero inaccurate acceptances, then most accurate acceptances, then conservative ties.
    return min(candidates, key=lambda c: (c['summary']['confident_but_inaccurate'],
                                         -c['summary']['all_four_within_tolerance'],
                                         -c['point_conf'], -c['board_conf']))


def collect(detector, data, split):
    records = []
    for image_path, label_path in split_records(data, split):
        image = read_image(image_path)
        box, points = read_label(label_path)
        xyxy = np.r_[box[:2] - box[2:] / 2, box[:2] + box[2:] / 2] * np.tile(image.size, 2)
        gt_points = points * [image.width, image.height, 1]
        boxes, scores, predictions = detector.raw(image)
        records.append(dict(image=image_path.name, source=image_path, size=image.size,
                            gt_box=xyxy, gt_points=gt_points, boxes=boxes,
                            scores=scores, points=predictions))
    return records


def save_samples(records, summary, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    # Save a few representative accuracy successes/failures, not every source photo.
    selected = []
    for accurate in [True, False]:
        selected.extend([i for i, row in enumerate(summary['rows']) if row['all_four_accurate'] == accurate][:2])
    for i in selected:
        record, row = records[i], summary['rows'][i]
        source = read_image(record['source'])
        source.thumbnail((500, 560))
        canvas = Image.new('RGB', (650, 680), 'white')
        canvas.paste(source, (0, 70))
        draw = ImageDraw.Draw(canvas)
        accuracy = f"all within {row['tolerance_px']:.1f}px per point" if row['all_four_accurate'] else 'not all within localization tolerance'
        draw.text((8, 5), f"{record['image']}: {row['status']} / {row['reason'] or accuracy}", fill='black')
        draw.text((8, 22), accuracy, fill='black')
        draw.text((8, 40), 'Cyan = label; red = highest-score candidate (may be rejected)', fill='black')
        scale = np.array(source.size) / np.array(record['size'])
        for j, p in enumerate(record['gt_points']):
            x, y = p[:2] * scale + [0, 70]
            draw.ellipse((x-5, y-5, x+5, y+5), outline='#00aacc', width=2)
            draw.text((x+6, y-10), f'L{j}', fill='#007788')
        if len(record['scores']):
            points = record['points'][int(np.argmax(record['scores']))]
            for j, p in enumerate(points):
                if np.isfinite(p).all():
                    x, y = p[:2] * scale + [0, 70]
                    draw.line((x-4, y-4, x+4, y+4), fill='red', width=2)
                    draw.line((x-4, y+4, x+4, y-4), fill='red', width=2)
                    draw.text((x+6, y+3), f'P{j} {p[2]:.2f}', fill='red')
        draw.text((8, 635), 'Photo: Adam Byerly (frettapper), micro-PCB Images v2 / CC BY 4.0', fill='black')
        draw.text((8, 651), 'Resized; labels and model predictions added by this project.', fill='black')
        canvas.save(destination / f"{Path(record['image']).stem}.jpg", quality=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--split', choices=['val', 'test'], default='val')
    parser.add_argument('--select', action='store_true')
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--samples')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--tolerance-fraction', type=float, default=.01)
    args = parser.parse_args()
    if args.select and args.split != 'val':
        parser.error('Threshold selection is permitted on validation data only')
    if not 0 < args.tolerance_fraction < 1:
        parser.error('Tolerance fraction must be in (0, 1)')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    config_path = Path(args.config)
    config = None if args.select else json.loads(config_path.read_text(encoding='utf-8'))
    imgsz = args.imgsz if config is None else config['imgsz']
    detector = LandmarkDetector(args.checkpoint, args.data, args.device, imgsz,
                                expected_sha256=config['checkpoint_sha256'] if config else None)
    dataset = audit(args.data)
    if config and (config['checkpoint_sha256'] != detector.sha256
                   or config['landmark_order'] != detector.names
                   or config['dataset_sha256'] != dataset['dataset_sha256']):
        raise ValueError('Frozen configuration does not match checkpoint/schema/dataset')
    if args.select and config_path.exists():
        parser.error('Refusing to overwrite a frozen configuration; choose a new file')
    records = collect(detector, args.data, args.split)
    if args.select:
        selected = select_thresholds(records, detector.names, args.tolerance_fraction)
        config = dict(checkpoint_sha256=detector.sha256, dataset_sha256=dataset['dataset_sha256'],
                      landmark_order=detector.names, imgsz=imgsz, selected_on='val',
                      board_conf=selected['board_conf'], point_conf=selected['point_conf'],
                      tolerance_fraction=args.tolerance_fraction, match_iou=.5,
                      selection_policy='min inaccurate accepted; max accurate accepted; conservative confidence ties',
                      validation_usable=selected['summary']['all_four_usable'],
                      validation_accurate=selected['summary']['all_four_within_tolerance'])
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    summary = summarize(records, detector.names, config['board_conf'], config['point_conf'], config['tolerance_fraction'])
    local_yaml = resolved_yaml(args.data, output.parent / f'{args.split}.resolved.yaml')
    metrics = detector.model.val(data=local_yaml, split=args.split, device=args.device,
                                 imgsz=imgsz, batch=4, workers=0, conf=.001, plots=False,
                                 project=str((output.parent / 'metrics').resolve()),
                                 name=args.split, exist_ok=True, save_json=False, verbose=False)
    summary.update(split=args.split, configuration=config, dataset=dataset, pose_metrics=metrics.results_dict,
                   localization_matching='Highest-confidence prediction with box IoU >= 0.5 at score >= 0.001; visible labels only; independent of runtime acceptance',
                   oks_sigma='Ultralytics custom-four-point default: 1/4 for each landmark')
    output.write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if args.samples:
        save_samples(records, summary, args.samples)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
