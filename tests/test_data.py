import tempfile
import unittest
from pathlib import Path

import yaml
from PIL import Image

from pcb_landmarks.data import audit, read_label


LABEL = '0 0.5 0.5 0.8 0.8 0.2 0.2 2 0.8 0.2 2 0.8 0.8 2 0.2 0.8 2'


class DataTests(unittest.TestCase):
    def test_label_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'label.txt'
            path.write_text(LABEL)
            box, points = read_label(path)
            self.assertEqual(points.shape, (4, 3))
            self.assertEqual(box.tolist(), [0.5, 0.5, 0.8, 0.8])
            for bad in [LABEL.replace('0.2', '1.2', 1), LABEL + ' 2',
                        LABEL.replace(' 2', ' 3', 1), '1' + LABEL[1:],
                        LABEL.replace('0.5', 'nan', 1), LABEL + '\n' + LABEL]:
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    read_label(path)

    def test_split_leakage_and_missing_pairs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = dict(train='images/train', val='images/val', test='images/test',
                          names={0: 'pcb'}, kpt_shape=[4, 3],
                          kpt_names={0: ['a', 'b', 'c', 'd']})
            data = root / 'dataset.yaml'
            data.write_text(yaml.safe_dump(config))
            rows = ['image,pose_label,layout_id,layout_family,split,width_px,height_px']
            for i, split in enumerate(['train', 'val', 'test']):
                (root / 'images' / split).mkdir(parents=True)
                (root / 'labels' / split).mkdir(parents=True)
                Image.new('RGB', (20, 20), (i * 80, 0, 0)).save(root / f'images/{split}/x.png')
                (root / f'labels/{split}/x.txt').write_text(LABEL + '\n')
                rows.append(f'images/{split}/x.png,labels/{split}/x.txt,{split},{split},{split},20,20')
            (root / 'manifest.csv').write_text('\n'.join(rows))
            self.assertEqual(audit(data)['split_sizes'], dict(train=1, val=1, test=1))
            for text_path in [data, *root.glob('labels/*/*.txt')]:
                text_path.write_bytes(text_path.read_bytes().replace(b'\r\n', b'\n'))
            fingerprint = audit(data)['dataset_sha256']
            for text_path in [data, *root.glob('labels/*/*.txt')]:
                text_path.write_bytes(text_path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            self.assertEqual(audit(data)['dataset_sha256'], fingerprint)
            (root / 'images/val/x.png').write_bytes((root / 'images/train/x.png').read_bytes())
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                audit(data)
            (root / 'labels/test/x.txt').unlink()
            with self.assertRaises(ValueError):
                audit(data)


if __name__ == '__main__':
    unittest.main()
