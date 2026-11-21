"""Reproducible YOLO26n Pose fine-tuning; initial setup may download official weights."""
import argparse
import json
from pathlib import Path

from .data import DEFAULT_DATA, audit, resolved_yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--weights', default='models/yolo26n-pose.pt')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--epochs', type=int, default=150)
    parser.add_argument('--batch', type=int, default=4)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--patience', type=int, default=30)
    parser.add_argument('--project', default='runs/landmarks')
    parser.add_argument('--name', default='full')
    args = parser.parse_args()
    if min(args.imgsz, args.epochs, args.batch) <= 0:
        parser.error('imgsz, epochs and batch must be positive')
    report = audit(args.data)
    import torch
    from ultralytics import YOLO
    from ultralytics.utils import SETTINGS
    SETTINGS.update({'sync': False})
    device = ('0' if torch.cuda.is_available() else 'cpu') if args.device == 'auto' else args.device
    run = Path(args.project) / args.name
    if run.exists():
        parser.error(f'Run already exists: {run}; choose a new --name')
    run.mkdir(parents=True)
    data = resolved_yaml(args.data, run / 'dataset.resolved.yaml')
    model = YOLO(args.weights, task='pose')
    metrics = model.train(data=data, imgsz=args.imgsz, epochs=args.epochs,
                          batch=args.batch, nbs=args.batch, device=device, seed=args.seed,
                          deterministic=True, workers=0, fliplr=0.0, flipud=0.0,
                          amp=False, optimizer='AdamW', lr0=0.001, lrf=0.01, warmup_bias_lr=0.001,
                          patience=args.patience, project=str(Path(args.project).resolve()), name=args.name,
                          exist_ok=True, val=True, plots=False, save=True, cache=False)
    best = run / 'weights/best.pt'
    if not best.is_file() or not (run / 'weights/last.pt').is_file():
        raise RuntimeError('Training finished without expected checkpoints')
    summary = dict(settings=vars(args) | {'device': device}, dataset=report,
                   cuda_available=torch.cuda.is_available(), torch=torch.__version__,
                   gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                   metrics=metrics.results_dict, checkpoint=best.as_posix())
    (run / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
