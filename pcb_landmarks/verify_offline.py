"""Verify local model loading and inference with networking blocked in a fresh process."""
import argparse
import json
import socket
from pathlib import Path
from unittest.mock import patch

from .infer import LandmarkDetector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--sources', nargs='+', required=True)
    parser.add_argument('--generic-checkpoint')
    parser.add_argument('--components', action='store_true', help='Also verify local ParsaVictor component inference')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    attempts, results = [], []

    def blocked(*arguments, **kwargs):
        attempts.append('network_attempt')
        raise OSError('Networking blocked by offline verification')

    with patch.object(socket, 'getaddrinfo', blocked), \
         patch.object(socket, 'create_connection', blocked), \
         patch.object(socket.socket, 'connect', blocked), \
         patch.object(socket.socket, 'connect_ex', blocked):
        detector = LandmarkDetector(args.checkpoint, imgsz=config['imgsz'], device='cpu',
                                    expected_sha256=config['checkpoint_sha256'])
        assert detector.sha256 == config['checkpoint_sha256'], 'Checkpoint hash mismatch'
        assert detector.names == config['landmark_order'], 'Landmark order mismatch'
        for source in args.sources:
            result = detector.predict(source, config['board_conf'], config['point_conf'])
            assert result['status'] in ['ok', 'failure']
            assert len(result['landmarks']) == (4 if result['status'] == 'ok' else 0)
            results.append(dict(image=Path(source).name, **result))
            if args.components:
                from .component_detection import propose_components
                from .data import read_image
                proposals = propose_components(read_image(source))
                results[-1]['component_count'] = len(proposals['components'])
                results[-1]['component_method'] = proposals['method']
        generic_rejected = None
        if args.generic_checkpoint:
            try:
                LandmarkDetector(args.generic_checkpoint)
            except ValueError:
                generic_rejected = True
            else:
                raise AssertionError('Generic pose weights must be rejected')
    assert not attempts, f'Unexpected network attempts: {attempts}'
    report = dict(device='cpu', network_attempts=len(attempts),
                  generic_pose_weights_rejected=generic_rejected, results=results)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
