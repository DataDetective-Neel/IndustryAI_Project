"""Read the Step 2 schema without changing labels, identities or splits."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw


DEFAULT_DATA = 'PCB_Dataset_Pilot/dataset.yaml'


def load_data(path):
    path = Path(path).resolve(strict=True)
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    root = Path(config.get('path', path.parent))
    if not root.is_absolute():
        root = path.parent / root
    names = config.get('names')
    if names not in ({0: 'pcb'}, ['pcb']) or config.get('kpt_shape') != [4, 3]:
        raise ValueError('Expected Step 2 class 0=pcb and kpt_shape [4, 3]')
    landmarks = config.get('kpt_names', {}).get(0, [])
    if len(landmarks) != 4 or len(set(landmarks)) != 4:
        raise ValueError('Expected four distinct landmark names in dataset order')
    return config, root.resolve(), landmarks


def read_label(path):
    lines = Path(path).read_text(encoding='utf-8').strip().splitlines()
    if len(lines) != 1:
        raise ValueError(f'{Path(path).name}: expected exactly one board')
    values = np.array([float(v) for v in lines[0].split()])
    if values.shape != (17,) or not np.isfinite(values).all() or values[0] != 0:
        raise ValueError(f'{Path(path).name}: expected class 0, box, four x/y/visibility triples')
    box, points = values[1:5], values[5:].reshape(4, 3)
    if (box < 0).any() or (box > 1).any() or (box[2:] <= 0).any():
        raise ValueError(f'{Path(path).name}: invalid normalized box')
    if (box[:2] - box[2:] / 2 < -1e-6).any() or (box[:2] + box[2:] / 2 > 1 + 1e-6).any():
        raise ValueError(f'{Path(path).name}: box extends outside image')
    if (points[:, :2] < 0).any() or (points[:, :2] > 1).any():
        raise ValueError(f'{Path(path).name}: keypoint outside normalized range')
    if not np.isin(points[:, 2], [0, 1, 2]).all():
        raise ValueError(f'{Path(path).name}: visibility must be 0, 1 or 2')
    return box, points


def read_image(path):
    with Image.open(path) as image:
        if image.getexif().get(274, 1) != 1:
            raise ValueError('Image EXIF orientation must be normalized before annotation/inference')
        return image.convert('RGB')


def split_records(data, split):
    config, root, _ = load_data(data)
    image_dir = root / config[split]
    if not image_dir.is_dir():
        raise ValueError(f'{split}: configured image directory is missing')
    images = sorted(p for p in image_dir.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png'})
    label_dir = image_dir.parent.parent / 'labels' / image_dir.name
    if not images or len({p.stem for p in images}) != len(images):
        raise ValueError(f'{split}: empty images or duplicate label stems')
    labels = {p.stem for p in label_dir.glob('*.txt')}
    if labels != {p.stem for p in images}:
        raise ValueError(f'{split}: image/label pairs do not match')
    return [(p, label_dir / (p.stem + '.txt')) for p in images]


def audit(data, preview_dir=None):
    config, root, landmarks = load_data(data)
    with (root / 'manifest.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    manifest = {r['image']: r for r in rows}
    if len(manifest) != len(rows):
        raise ValueError('Duplicate manifest rows')
    hashes, layouts, families, seen = {}, {}, {}, set()
    report = dict(split_sizes={}, layouts={}, landmark_order=landmarks,
                  visibility_counts={'0': 0, '1': 0, '2': 0}, duplicate_images_across_splits=0)
    digest = hashlib.sha256(Path(data).read_bytes())
    for split in ['train', 'val', 'test']:
        records, tiles = split_records(data, split), []
        report['split_sizes'][split] = len(records)
        report['layouts'][split] = sorted({manifest[p.relative_to(root).as_posix()]['layout_id'] for p, _ in records})
        for image_path, label_path in records:
            image, (_, points) = read_image(image_path), read_label(label_path)
            relative = image_path.relative_to(root).as_posix()
            row = manifest.get(relative)
            if row is None or row['split'] != split or row['pose_label'] != label_path.relative_to(root).as_posix():
                raise ValueError(f'{relative}: missing or inconsistent manifest entry')
            if image.size != (int(row['width_px']), int(row['height_px'])):
                raise ValueError(f'{relative}: dimensions disagree with manifest')
            seen.add(relative)
            for field, groups in [('layout_id', layouts), ('layout_family', families)]:
                value = row[field]
                if value in groups and groups[value] != split:
                    raise ValueError(f'{field} {value}: leaks across splits')
                groups[value] = split
            for value in [hashlib.sha256(image_path.read_bytes()).hexdigest(),
                          hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()]:
                if value in hashes and hashes[value] != split:
                    raise ValueError(f'{relative}: duplicate image across splits')
                hashes[value] = split
            digest.update(relative.encode() + image_path.read_bytes() + label_path.read_bytes())
            for visibility in points[:, 2]:
                report['visibility_counts'][str(int(visibility))] += 1
            if preview_dir:
                image.thumbnail((270, 310))
                tile = Image.new('RGB', (300, 350), 'white')
                tile.paste(image, (0, 30))
                draw = ImageDraw.Draw(tile)
                draw.text((5, 5), f'{image_path.name} / {split}', fill='black')
                for i, (x, y, v) in enumerate(points):
                    if v:
                        x, y = x * image.width, 30 + y * image.height
                        draw.ellipse((x-5, y-5, x+5, y+5), outline='red', width=2)
                        draw.text((x+6, y-7), str(i), fill='red')
                tiles.append(tile)
        if preview_dir:
            out = Path(preview_dir)
            out.mkdir(parents=True, exist_ok=True)
            for page in range(0, len(tiles), 8):
                sheet = Image.new('RGB', (1200, 700), '#eeeeee')
                for j, tile in enumerate(tiles[page:page+8]):
                    sheet.paste(tile, ((j % 4) * 300, (j // 4) * 350))
                sheet.save(out / f'{split}-{page // 8}.jpg')
    if seen != set(manifest):
        raise ValueError('Manifest contains unconfigured images')
    report['dataset_sha256'] = digest.hexdigest()
    report['layout_and_family_separation'] = 'passed'
    return report


def resolved_yaml(data, output):
    config, root, _ = load_data(data)
    config['path'] = root.as_posix()
    Path(output).write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    return str(Path(output).resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--previews', default=None)
    parser.add_argument('--output', default=None)
    args = parser.parse_args()
    report = audit(args.data, args.previews)
    payload = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload + '\n', encoding='utf-8')
    print(payload)


if __name__ == '__main__':
    main()
