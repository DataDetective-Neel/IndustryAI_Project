"""Loopback PCB inspection API; shared CLI algorithms, local assets only."""
import json
import os
import re
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import cv2
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .align import align_images, blend_overlay
from .compare import _validate_regions, annotated_overlay, compare_regions, load_config
from .data import open_image, read_image
from .infer import LandmarkDetector


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = Path(os.environ.get('PCB_CHECKPOINT', ROOT/'runs/landmarks/full/weights/best.pt'))
MAX_UPLOAD = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_PHOTOS = 15
MODEL_LOCK = threading.Lock()


class PhotoPoints(BaseModel):
    photo_id: str
    points: list[list[float]] = Field(default_factory=list, max_length=4)


class InspectionRequest(BaseModel):
    reference_id: str
    reference_points: list[list[float]] = Field(default_factory=list, max_length=4)
    inspections: list[PhotoPoints] = Field(min_length=1, max_length=MAX_PHOTOS)
    components: list[dict] = Field(min_length=1, max_length=100)
    mode: Literal['manual', 'automatic']
    sharpen: StrictBool = False
    synthetic: StrictBool = False


@lru_cache(maxsize=1)
def _detector(checkpoint):
    config = json.loads((ROOT/'configs/landmarks.json').read_text())
    detector = LandmarkDetector(checkpoint, ROOT/'PCB_Dataset_Pilot/dataset.yaml', 'cpu', config['imgsz'],
                                expected_sha256=config['checkpoint_sha256'])
    if detector.names != config['landmark_order']:
        raise ValueError('Frozen configuration landmark order does not match checkpoint')
    return detector, config


def create_app(storage=None):
    storage = Path(storage) if storage is not None else ROOT/'runs/web'
    (storage/'photos').mkdir(parents=True, exist_ok=True)
    (storage/'batches').mkdir(exist_ok=True)
    app = FastAPI(title='Local PCB inspection', docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_requests(request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if origin and origin not in ['http://127.0.0.1:5173', 'http://localhost:5173',
                                         'http://127.0.0.1:8000', 'http://localhost:8000']:
                return JSONResponse({'detail': 'Only local app origins are accepted'}, status_code=403)
            length = request.headers.get('content-length')
            if length is None or not length.isdecimal():
                return JSONResponse({'detail': 'Content-Length is required'}, status_code=411)
            if int(length) > MAX_UPLOAD + 1024*1024:
                return JSONResponse({'detail': 'Request exceeds local upload limit'}, status_code=413)
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def directory(kind, identifier):
        if not re.fullmatch(r'[0-9a-f]{32}', identifier):
            raise HTTPException(404, 'Unknown local asset ID')
        path = storage/kind/identifier
        if not path.is_dir():
            raise HTTPException(404, 'Unknown local asset ID')
        return path

    def photo(identifier):
        path = directory('photos', identifier)
        return json.loads((path/'photo.json').read_text()), path

    def detect(identifier):
        record, path = photo(identifier)
        if record['error']:
            return dict(status='failure', reason=record['error'], landmarks=[])
        if not CHECKPOINT.is_file():
            return dict(status='failure', reason=f'checkpoint_unavailable: {CHECKPOINT.resolve()}', landmarks=[])
        with MODEL_LOCK:
            try:
                detector, config = _detector(str(CHECKPOINT.resolve()))
                result = detector.predict(path/'image.png', config['board_conf'], config['point_conf'])
                (path/'landmarks.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
                return result
            except Exception as error:
                return dict(status='failure', reason=f'{type(error).__name__}: {error}'.replace(str(ROOT), '<project>'),
                            landmarks=[])

    @app.get('/api/health')
    def health():
        names = json.loads((ROOT/'configs/landmarks.json').read_text())['landmark_order']
        return dict(status='ok', landmark_names=names,
                    comparison=load_config(ROOT/'configs/comparison.json'),
                    checkpoint_available=CHECKPOINT.is_file(), checkpoint_path=str(CHECKPOINT.resolve()), max_photos=MAX_PHOTOS,
                    max_upload_bytes=MAX_UPLOAD, max_pixels=MAX_PIXELS)

    @app.post('/api/photos')
    def upload(image: UploadFile):
        content = image.file.read(MAX_UPLOAD+1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, 'Photo exceeds 12 MiB upload limit')
        identifier = uuid.uuid4().hex
        path = storage/'photos'/identifier
        path.mkdir()
        source = path/'source'
        source.write_bytes(content)
        record = dict(id=identifier, filename=(image.filename or 'photo').replace('\\', '/').split('/')[-1],
                      width=None, height=None, error=None, image_url=None)
        try:
            with open_image(source) as header:
                if header.format not in ['JPEG', 'PNG']:
                    raise ValueError('Only JPEG and PNG photos are supported')
                if header.width*header.height > MAX_PIXELS or min(header.size) < 2:
                    raise ValueError('Decoded photo must be at least 2x2 and at most 20 million pixels')
            decoded = read_image(source)
            decoded.save(path/'image.png')
            record.update(width=decoded.width, height=decoded.height, image_url=f'/api/photos/{identifier}/image')
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            record['error'] = ('ImageDecodeError: corrupt or unsupported JPEG/PNG' if isinstance(error, UnidentifiedImageError)
                               else f'{type(error).__name__}: {error}'.replace(str(path), '<upload>'))
        finally:
            source.unlink()
            image.file.close()
        (path/'photo.json').write_text(json.dumps(record), encoding='utf-8')
        return record

    @app.get('/api/photos/{identifier}/image')
    def original(identifier: str):
        record, path = photo(identifier)
        if record['error']:
            raise HTTPException(404, record['error'])
        return FileResponse(path/'image.png', media_type='image/png')

    @app.get('/api/photos/{identifier}/regions')
    def saved_regions(identifier: str):
        record, path = photo(identifier)
        preset_path = ROOT/'configs/components-ECCC5.json'
        if not preset_path.is_file():
            raise HTTPException(404, 'No saved regions for this reference')
        preset = json.loads(preset_path.read_text())
        source = ROOT/preset['reference_image']
        if record['error'] or not source.is_file():
            raise HTTPException(404, 'No saved regions for this reference')
        if not np.array_equal(np.asarray(read_image(path/'image.png')), np.asarray(read_image(source))):
            raise HTTPException(404, 'Saved regions require the exact known-good ECCC5 reference')
        return preset

    @app.post('/api/landmarks/{identifier}')
    def landmarks(identifier: str):
        return detect(identifier)

    @app.post('/api/inspections')
    def inspect(request: InspectionRequest):
        reference, reference_path = photo(request.reference_id)
        config = load_config(ROOT/'configs/comparison.json')
        ref_image = read_image(reference_path/'image.png') if not reference['error'] else None
        regions = dict(reference_image=reference['filename'],
                       reference_wh_px=[reference['width'], reference['height']], components=request.components)
        try:
            _validate_regions(regions, (reference['width'], reference['height']))
            json.dumps(request.model_dump(), allow_nan=False)
            for part in request.components:
                if len(part['id']) > 100 or len(part['name']) > 120 or len(part.get('review_reason', '')) > 500:
                    raise ValueError('Annotation limits: id 100, name 120, review reason 500 characters')
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        batch_id = uuid.uuid4().hex
        batch_path = storage/'batches'/batch_id
        batch_path.mkdir()
        reference_detection = detect(request.reference_id) if request.mode == 'automatic' else None
        results = []
        for index, item in enumerate(request.inspections):
            name = item.photo_id
            result = dict(photo_id=item.photo_id, filename=name, outcome='review', review_required=True,
                          alignment=dict(status='failure', reason=None), components=[],
                          alignment_overlay_url=None, component_overlay_url=None)
            try:
                current, current_path = photo(item.photo_id)
                result['filename'] = current['filename']
                if reference['error'] or current['error']:
                    result['outcome'] = 'error'
                    raise ValueError(reference['error'] or current['error'])
                rp, ip = request.reference_points, item.points
                if request.mode == 'automatic':
                    detection = detect(item.photo_id)
                    result['landmark_diagnostics'] = dict(reference=reference_detection, inspection=detection)
                    if reference_detection['status'] != 'ok':
                        raise ValueError('Reference: ' + reference_detection['reason'])
                    if detection['status'] != 'ok':
                        raise ValueError(detection['reason'])
                    rp = [[p['x'], p['y']] for p in reference_detection['landmarks']]
                    ip = [[p['x'], p['y']] for p in detection['landmarks']]
                aligned, homography, mask = align_images(ref_image, read_image(current_path/'image.png'), rp, ip)
                alignment = dict(status='ok', reference_wh=list(ref_image.size),
                                 homography_inspection_to_reference=homography.tolist(),
                                 valid_overlap_fraction=float((mask > 0).mean()))
                comparison = compare_regions(ref_image, aligned, mask, regions, config, alignment, request.sharpen)
                output = batch_path/str(index)
                output.mkdir()
                Image.fromarray(blend_overlay(np.asarray(ref_image), aligned, mask)).save(output/'alignment.png')
                annotated_overlay(ref_image, aligned, mask, comparison).save(output/'components.png')
                result.update(comparison, photo_id=item.photo_id, filename=current['filename'], alignment=alignment,
                              alignment_overlay_url=f'/api/batches/{batch_id}/{index}/alignment',
                              component_overlay_url=f'/api/batches/{batch_id}/{index}/components')
            except Exception as error:
                if not isinstance(error, (ValueError, cv2.error)):
                    result['outcome'] = 'error'
                reason = str(error) if isinstance(error, (ValueError, HTTPException)) else f'{type(error).__name__}: {error}'
                result['alignment'] = dict(status='failure', reason=reason)
                result['components'] = [dict(id=p.get('id'), name=p.get('name'), bbox_xyxy_px=p.get('bbox_xyxy_px'),
                                             status='not_evaluated', display_status='Not evaluated', score=None,
                                             overlap=None, reason=reason) for p in request.components]
            results.append(result)
        batch = dict(batch_id=batch_id, reference_id=request.reference_id, mode=request.mode,
                     synthetic=request.synthetic, sharpening_enabled=request.sharpen,
                     annotations=request.model_dump(),
                     thresholds_provisional=True, comparison_config=config, photos=results,
                     report_url=f'/api/batches/{batch_id}/report')
        (batch_path/'report.json').write_text(json.dumps(batch, indent=2, allow_nan=False), encoding='utf-8')
        return batch

    @app.get('/api/batches/{identifier}/report')
    def report(identifier: str):
        return FileResponse(directory('batches', identifier)/'report.json', media_type='application/json')

    @app.get('/api/batches/{identifier}/{index}/{kind}')
    def result_asset(identifier: str, index: int, kind: str):
        if index not in range(MAX_PHOTOS) or kind not in ['alignment', 'components']:
            raise HTTPException(404, 'Unknown result asset')
        path = directory('batches', identifier)/str(index)/f'{kind}.png'
        if not path.is_file():
            raise HTTPException(404, 'No overlay for this photo')
        return FileResponse(path, media_type='image/png')

    app.mount('/assets', StaticFiles(directory=ROOT/'frontend/dist/assets', check_dir=False), name='frontend-assets')

    @app.get('/')
    def index():
        path = ROOT/'frontend/dist/index.html'
        if not path.is_file():
            raise HTTPException(503, 'Build frontend with npm run build, or use the Vite development server')
        return FileResponse(path)

    return app


app = create_app()
