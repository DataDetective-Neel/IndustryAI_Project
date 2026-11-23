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
from fastapi import FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .align import _points, align_images, blend_overlay
from .registration import (automatic_reference, board_polygon, surface_mask, reference_features,
                           register_inspection, match_surfaces, verify_alignment)
from .registration import refine_manual_registration
from .compare import _validate_regions, annotated_overlay, compare_regions, load_config
from .compatibility import check_compatibility, identify_board
from .data import open_image, read_image
from .infer import LandmarkDetector
from .platform_store import AOIStore, ROLES
from .simulator import LineSimulator
from .component_detection import import_component_map, propose_components
from .correspondence import transform_components


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = Path(os.environ.get('PCB_CHECKPOINT', ROOT/json.loads(
    (ROOT/'configs/landmarks.json').read_text()).get('checkpoint_path', 'runs/landmarks/full/weights/best.pt')))
MAX_UPLOAD = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_PHOTOS = 15
MAX_IMPORT = MAX_PHOTOS * MAX_UPLOAD + 2 * 1024 * 1024
MODEL_LOCK = threading.Lock()


class PhotoPoints(BaseModel):
    photo_id: str
    points: list[list[float]] = Field(default_factory=list, max_length=4)


class ReferenceSetup(BaseModel):
    points: list[list[float]] = Field(min_length=4, max_length=4)
    board_polygon: list[list[float]] = Field(min_length=3, max_length=12)


class InspectionRequest(BaseModel):
    reference_id: str
    reference_points: list[list[float]] = Field(default_factory=list, max_length=4)
    inspections: list[PhotoPoints] = Field(min_length=1, max_length=MAX_PHOTOS)
    components: list[dict] = Field(min_length=1, max_length=1000)
    mode: Literal['manual', 'automatic']
    sharpen: StrictBool = False
    synthetic: StrictBool = False
    simulated: StrictBool = False


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal['administrator', 'supervisor', 'operator']
    password: str = Field(min_length=10, max_length=200)


class DecisionRequest(BaseModel):
    decision: Literal['confirmed_reject', 'false_alarm']
    note: str = Field(default='', max_length=500)


class GoldenConfigRequest(BaseModel):
    reference_id: str = Field(min_length=32, max_length=32)
    components: list[dict] = Field(min_length=1, max_length=1000)
    mode: Literal['manual', 'automatic'] = 'automatic'
    sharpen: StrictBool = False


class ComponentProposalRequest(BaseModel):
    board_polygon: list[list[float]] = Field(default_factory=list, max_length=12)


class PreferencesRequest(BaseModel):
    alarm_sound: bool | None = None
    inspection_interval: float | None = Field(default=None, ge=0.5, le=120)
    simulation_directory: str | None = Field(default=None, max_length=500)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class SimulationStart(BaseModel):
    dataset_directory: str = Field(min_length=1, max_length=500)
    interval: float = Field(default=3.0, ge=0.5, le=120)


@lru_cache(maxsize=1)
def _detector(checkpoint):
    config = json.loads((ROOT/'configs/landmarks.json').read_text())
    detector = LandmarkDetector(checkpoint, ROOT/'PCB_Dataset_Pilot/dataset.yaml', 'cpu', config['imgsz'],
                                expected_sha256=config['checkpoint_sha256'],
                                refine_mounting_holes=config.get('refine_mounting_holes', False),
                                mounting_reference=(ROOT/'configs'/config['mounting_reference']
                                                    if config.get('mounting_reference') else None),
                                calibrated_mounting_holes=config.get('calibrated_mounting_holes', False))
    if detector.names != config['landmark_order']:
        raise ValueError('Frozen configuration landmark order does not match checkpoint')
    return detector, config


def create_app(storage=None):
    storage = Path(storage) if storage is not None else ROOT/'runs/web'
    (storage/'photos').mkdir(parents=True, exist_ok=True)
    (storage/'batches').mkdir(exist_ok=True)
    store = AOIStore(storage/'aoi.db')
    store.bootstrap_admin()
    app = FastAPI(title='Local PCB inspection', docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_requests(request, call_next):
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/') and origin not in ['http://127.0.0.1:5173', 'http://localhost:5173',
                                         'http://127.0.0.1:8000', 'http://localhost:8000']:
                return JSONResponse({'detail': 'Only local app origins are accepted'}, status_code=403)
            length = request.headers.get('content-length')
            if length is None or not length.isdecimal():
                return JSONResponse({'detail': 'Content-Length is required'}, status_code=411)
            limit = MAX_IMPORT if request.url.path == '/api/simulation/import' else MAX_UPLOAD + 1024*1024
            if int(length) > limit:
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

    def current_user(authorization):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Sign in is required')
        user = store.user_for_token(authorization[7:])
        if not user:
            raise HTTPException(401, 'Session is invalid')
        return user

    def authorize(authorization, roles):
        user = current_user(authorization)
        if user['role'] not in roles:
            raise HTTPException(403, 'Role does not permit this action')
        return user

    @app.post('/api/auth/login')
    def login(request: LoginRequest):
        authenticated = store.authenticate(request.username, request.password)
        if not authenticated:
            raise HTTPException(401, 'Invalid username or password')
        token, user = authenticated
        return {'token': token, 'user': user}

    @app.get('/api/auth/me')
    def me(authorization: str | None = Header(default=None)):
        return current_user(authorization)

    @app.get('/api/users')
    def users(authorization: str | None = Header(default=None)):
        authorize(authorization, {'administrator'})
        return {'users': store.list_users(), 'roles': sorted(ROLES)}

    @app.post('/api/users')
    def add_user(request: UserCreate, authorization: str | None = Header(default=None)):
        authorize(authorization, {'administrator'})
        try:
            store.create_user(request.username, request.display_name, request.role, request.password)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            if 'UNIQUE constraint' in str(error):
                raise HTTPException(409, 'Username already exists') from error
            raise
        return {'created': request.username.lower()}

    @app.patch('/api/account/preferences')
    def preferences(request: PreferencesRequest, authorization: str | None = Header(default=None)):
        user = current_user(authorization)
        values = request.model_dump(exclude_none=True)
        return store.update_preferences(user['username'], values)

    @app.post('/api/account/password')
    def password(request: PasswordChange, authorization: str | None = Header(default=None)):
        user = current_user(authorization)
        try:
            store.change_password(user['username'], request.current_password, request.new_password)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {'changed': True, 'sign_in_required': True}

    @app.get('/api/dashboard')
    def dashboard(authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        data = store.dashboard()
        data['line'] = simulator.state()
        return data

    @app.get('/api/reviews')
    def reviews(authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        items = store.pending()
        for item in items:
            item['evidence'] = json.loads(item.pop('evidence_json'))
        return {'reviews': items}

    @app.post('/api/reviews/{inspection_id:path}/decision')
    def review_decision(inspection_id: str, request: DecisionRequest,
                        authorization: str | None = Header(default=None)):
        user = authorize(authorization, ROLES)
        try:
            store.decide(inspection_id, request.decision, user['username'], request.note)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {'inspection_id': inspection_id, 'decision': request.decision}

    @app.get('/api/golden-config')
    def golden_config(authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        config = store.golden()
        if not config:
            raise HTTPException(404, 'No golden configuration saved')
        record, path = photo(config['reference_id'])
        setup = (json.loads((path/'reference.json').read_text())
                 if (path/'reference.json').is_file() else {})
        config['reference'] = {**record, **setup}
        return config

    @app.post('/api/golden-config')
    def save_golden_config(request: GoldenConfigRequest,
                           authorization: str | None = Header(default=None)):
        nonlocal live_reference
        user = authorize(authorization, {'administrator', 'supervisor'})
        _, reference_path = photo(request.reference_id)
        if not (reference_path/'reference.json').is_file():
            raise HTTPException(422, 'Confirm reference landmarks and board outline before saving')
        config = request.model_dump(exclude={'reference_id'})
        try:
            record, _ = photo(request.reference_id)
            size = (record['width'], record['height'])
            _validate_regions({'reference_wh_px': list(size), 'components': config['components']}, size)
            if any(component.get('candidate_status') == 'UNKNOWN' for component in config['components']):
                raise ValueError('Accept, edit, or remove every UNKNOWN component proposal before saving')
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        with live_reference_lock:
            store.save_golden(request.reference_id, config, user['username'])
            live_reference = None
        return golden_config(authorization)

    @app.delete('/api/golden-config')
    def clear_golden_config(authorization: str | None = Header(default=None)):
        nonlocal live_reference
        authorize(authorization, {'administrator', 'supervisor'})
        with live_reference_lock:
            store.clear_golden()
            live_reference = None
        return {'cleared': True}

    def detect(identifier):
        record, path = photo(identifier)
        if record['error']:
            return dict(status='failure', reason=record['error'], landmarks=[])
        if not CHECKPOINT.is_file():
            return dict(status='failure', reason=f'checkpoint_unavailable: {CHECKPOINT.resolve()}', landmarks=[],
                        checkpoint_available=False, model_inference_ran=False, verification_status='unavailable')
        with MODEL_LOCK:
            try:
                detector, config = _detector(str(CHECKPOINT.resolve()))
                result = detector.predict(path/'image.png', config['board_conf'], config['point_conf'])
                result['checkpoint_available'] = True
                (path/'landmarks.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
                return result
            except Exception as error:
                return dict(status='failure', reason=f'{type(error).__name__}: {error}'.replace(str(ROOT), '<project>'),
                            landmarks=[])

    @lru_cache(maxsize=4)
    def cached_reference(identifier, polygon_json):
        _, path = photo(identifier)
        return reference_features(read_image(path/'image.png'), json.loads(polygon_json))

    @app.get('/api/references/{identifier}')
    def reference_setup(identifier: str):
        record, path = photo(identifier)
        if (path/'reference.json').is_file():
            return json.loads((path/'reference.json').read_text())
        polygon, reason = [], None
        if not record['error']:
            try:
                polygon = board_polygon(read_image(path/'image.png'))
            except ValueError as error:
                reason = str(error)
        return dict(points=[], board_polygon=polygon, confirmed=False, reason=reason)

    @app.post('/api/references/{identifier}')
    def save_reference(identifier: str, setup: ReferenceSetup):
        record, path = photo(identifier)
        try:
            if record['error']:
                raise ValueError(record['error'])
            image = read_image(path/'image.png')
            points = _points(setup.points, np.asarray(image), 'reference')
            surface_mask(image, setup.board_polygon)
            if any(cv2.pointPolygonTest(np.float32(setup.board_polygon), (float(x), float(y)), False) < 0 for x, y in points):
                raise ValueError('Reference landmarks must be inside the PCB surface outline.')
            features = cached_reference(identifier, json.dumps(setup.board_polygon))
            saved = dict(points=setup.points, board_polygon=setup.board_polygon, confirmed=True,
                         coordinate_system='decoded_original_image_pixels',
                         feature_count=len(features['xy']))
            temporary = path/'reference.tmp'
            temporary.write_text(json.dumps(saved, allow_nan=False), encoding='utf-8')
            temporary.replace(path/'reference.json')
            return saved
        except (ValueError, cv2.error) as error:
            raise HTTPException(422, str(error)) from error

    @app.post('/api/references/{identifier}/automatic')
    def automatic_reference_setup(identifier: str):
        record, path = photo(identifier)
        if (path/'reference.json').is_file():
            existing = json.loads((path/'reference.json').read_text())
            automatic_sources = {'automatic_board_corners', 'opencv_mounting_centers', 'yolo_landmarks'}
            if existing.get('source') not in automatic_sources or existing.get('geometry_version', 0) >= 2:
                return existing
        try:
            if record['error']:
                raise ValueError(record['error'])
            image = read_image(path/'image.png')
            proposal = automatic_reference(image)
            detection = detect(identifier)
            if detection['status'] == 'ok':
                points = [[p['x'], p['y']] for p in detection['landmarks']]
                try:
                    validated = _points(points, np.asarray(image), 'automatic YOLO reference')
                    polygon = np.float32(proposal['board_polygon'])
                    if (cv2.contourArea(validated.astype(np.float32)) >= .2*cv2.contourArea(polygon)
                            and all(cv2.pointPolygonTest(polygon, tuple(map(float, p)), False) >= 0 for p in validated)
                            and (proposal['landmark_kind'] != 'mounting_holes' or
                                 max(min(np.linalg.norm(np.asarray(p)-q) for q in proposal['points'])
                                     for p in points) <= max(4, .005*np.hypot(*np.asarray(image).shape[:2])))):
                        proposal.update(points=points, source='yolo_landmarks', landmark_kind='mounting_holes')
                except ValueError:
                    pass  # Validated geometry remains the independent fallback.
            saved = save_reference(identifier, ReferenceSetup(**proposal))
            saved.update(source=proposal['source'], landmark_kind=proposal['landmark_kind'],
                         geometry_version=2,
                         model_detection={k:detection.get(k) for k in ['status','reason','model_inference_ran','raw_board_predictions','verification_status','mounting_verification']})
            temporary = path/'reference.tmp'
            temporary.write_text(json.dumps(saved, allow_nan=False), encoding='utf-8')
            temporary.replace(path/'reference.json')
            return saved
        except (ValueError, cv2.error) as error:
            raise HTTPException(422, str(error)) from error

    @lru_cache(maxsize=8)
    def reference_component_detections(identifier, polygon_json):
        _, path = photo(identifier)
        return propose_components(read_image(path/'image.png'), json.loads(polygon_json))['components']

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

    @app.post('/api/photos/{identifier}/component-proposals')
    def component_proposals(identifier: str, request: ComponentProposalRequest | None = None):
        record, path = photo(identifier)
        if record['error']:
            raise HTTPException(422, record['error'])
        try:
            saved = (json.loads((path/'reference.json').read_text())
                     if (path/'reference.json').is_file() else None)
            polygon = request.board_polygon if request and len(request.board_polygon) >= 3 else (saved.get('board_polygon') if saved else None)
            result = propose_components(read_image(path/'image.png'),
                                        polygon)
            (path/'component-proposals.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            return result
        except (ValueError, cv2.error) as error:
            raise HTTPException(422, f'Component proposal failed: {error}') from error

    @app.post('/api/photos/{identifier}/component-map')
    def component_map(identifier: str, component_map: UploadFile):
        record, path = photo(identifier)
        if record['error']:
            raise HTTPException(422, record['error'])
        try:
            content = component_map.file.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError('Component map exceeds the 2 MiB limit')
            mapping = json.loads(content.decode('utf-8'))
            components = import_component_map(mapping, (record['width'], record['height']), record['filename'])
            saved = (json.loads((path/'reference.json').read_text())
                     if (path/'reference.json').is_file() else None)
            result = propose_components(read_image(path/'image.png'),
                                        saved.get('board_polygon') if saved else None,
                                        reference_components=components)
            # A supplied golden map owns its boxes and IDs; proposals must not
            # silently replace or resize the operator's reference configuration.
            result['components'] = [dict(part, candidate_status='UNKNOWN',
                                         proposal_evidence=dict(source='reference_component_map'))
                                    for part in components]
            result['candidate_count'] = len(components)
            result['method'] = 'Validated golden component map; operator acceptance required'
            result['imported_component_count'] = len(components)
            result['import_source'] = 'Antigravity golden_components.json (reference setup only)'
            (path/'component-proposals.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            return result
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, cv2.error) as error:
            raise HTTPException(422, f'Component map import failed: {error}') from error
        finally:
            component_map.file.close()

    @app.post('/api/landmarks/{identifier}')
    def landmarks(identifier: str, reference_id: str | None = None):
        detection = detect(identifier)
        if not reference_id or reference_id == identifier:
            return detection
        _, reference_path = photo(reference_id)
        record, current_path = photo(identifier)
        try:
            if record['error']:
                raise ValueError(record['error'])
            saved = automatic_reference_setup(reference_id)
            reference = read_image(reference_path/'image.png')
            current = read_image(current_path/'image.png')
            features = cached_reference(reference_id, json.dumps(saved['board_polygon']))
            _, _, _, registration = register_inspection(reference, current, saved['points'], features, detection)
            names = json.loads((ROOT/'configs/landmarks.json').read_text())['landmark_order']
            return dict(status='ok', reason=None, source=registration['source'],
                landmark_kind=registration.get('landmark_kind', 'model_detected'),
                verification_status='verified', verification=registration['verification'],
                landmarks=[dict(name=name, x=x, y=y, confidence=None) for name, (x,y) in
                           zip(names, registration['inspection_points'])], model_detection=detection)
        except (ValueError, cv2.error, HTTPException) as error:
            return dict(status='failure', reason=str(error), landmarks=[], model_detection=detection)

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
        reference_detection = None
        saved_reference = (json.loads((reference_path/'reference.json').read_text())
                           if (reference_path/'reference.json').is_file() else None)
        automatic_setup_error = None
        reference_layout = identify_board(ref_image) if ref_image is not None else None
        results = []
        for index, item in enumerate(request.inspections):
            name = item.photo_id
            result = dict(photo_id=item.photo_id, filename=name, outcome='review', review_required=True,
                          simulated=bool(request.simulated or request.synthetic),
                          alignment=dict(status='failure', reason=None), components=[],
                          components_evaluated=False, board_compatibility=None,
                          component_inspection=dict(status='not_attempted', reason=None, decision_count=0),
                          alignment_overlay_url=None, component_overlay_url=None)
            try:
                current, current_path = photo(item.photo_id)
                result['filename'] = current['filename']
                result['current_image_url'] = current['image_url']
                if reference['error'] or current['error']:
                    result['outcome'] = 'error'
                    raise ValueError(reference['error'] or current['error'])
                inspection_image = read_image(current_path/'image.png')
                inspection_layout = identify_board(inspection_image)
                compatibility = check_compatibility(reference_layout, inspection_layout)
                result['board_compatibility'] = compatibility
                if compatibility['status'] == 'DIFFERENT_BOARD':
                    result['component_inspection'].update(status='blocked', reason=compatibility['reason'])
                    result.update(outcome='DIFFERENT_BOARD' if compatibility['status'] == 'DIFFERENT_BOARD' else 'review',
                                  reason=compatibility['message'],
                                  alignment=dict(status='not_attempted',
                                                 reason='Board compatibility must pass before component scoring.'))
                    results.append(result)
                    continue
                if request.mode == 'automatic' and (not saved_reference or
                    (saved_reference.get('source') in {'automatic_board_corners', 'opencv_mounting_centers', 'yolo_landmarks'}
                     and saved_reference.get('geometry_version', 0) < 2)) and ref_image is not None:
                    try:
                        saved_reference = automatic_reference_setup(request.reference_id)
                    except HTTPException as error:
                        automatic_setup_error = error.detail
                rp = request.reference_points or (saved_reference['points'] if saved_reference else [])
                ip = item.points
                registration = None
                if request.mode == 'automatic' and saved_reference:
                    rp = saved_reference['points']
                    detection = detect(item.photo_id)
                    result['landmark_diagnostics'] = dict(reference=dict(status='confirmed', landmarks=rp,
                        source=saved_reference.get('source','manual'), landmark_kind=saved_reference.get('landmark_kind','manual'),
                        model_detection=saved_reference.get('model_detection')), inspection=detection)
                    features = cached_reference(request.reference_id, json.dumps(saved_reference['board_polygon']))
                    aligned, homography, mask, registration = register_inspection(
                        ref_image, inspection_image, rp, features, detection)
                else:
                    if request.mode == 'automatic':
                        if reference_detection is None:
                            reference_detection = detect(request.reference_id)
                        detection = detect(item.photo_id)
                        result['landmark_diagnostics'] = dict(reference=reference_detection, inspection=detection)
                        if reference_detection['status'] != 'ok':
                            raise ValueError('Reference: ' + (automatic_setup_error or reference_detection['reason']))
                        if detection['status'] != 'ok':
                            raise ValueError(detection['reason'])
                        rp = [[p['x'], p['y']] for p in reference_detection['landmarks']]
                        ip = [[p['x'], p['y']] for p in detection['landmarks']]
                    aligned, homography, mask = align_images(ref_image, inspection_image, rp, ip)
                    if request.mode == 'manual':
                        try:
                            polygon = saved_reference['board_polygon'] if saved_reference else board_polygon(ref_image)
                            refined = refine_manual_registration(ref_image, inspection_image, rp, ip,
                                cached_reference(request.reference_id, json.dumps(polygon)), homography)
                            if refined is not None:
                                aligned, homography, mask, registration = refined
                        except (ValueError, cv2.error):
                            pass  # Keep manual geometry; normal identity/quality gates still apply.
                alignment = dict(status='ok', reference_wh=list(ref_image.size),
                                 homography_inspection_to_reference=homography.tolist(),
                                 valid_overlap_fraction=float((mask > 0).mean()),
                                 verification_status='geometry_only', source='manual_landmarks' if request.mode == 'manual' else 'yolo_landmarks',
                                 reference_points=np.asarray(rp).tolist(), inspection_points=np.asarray(ip).tolist(),
                                 reference_landmark_kind=(saved_reference or {}).get('landmark_kind','manual'),
                                 landmark_kind='manual' if request.mode == 'manual' else 'model_detected')
                if registration:
                    alignment.update(registration)
                output = batch_path/str(index)
                output.mkdir()
                Image.fromarray(blend_overlay(np.asarray(ref_image), aligned, mask)).save(output/'alignment.png')
                difference = cv2.absdiff(np.asarray(ref_image), aligned)
                difference[mask == 0] = 0
                heatmap = cv2.applyColorMap(np.mean(difference, axis=2).astype(np.uint8), cv2.COLORMAP_TURBO)
                Image.fromarray(cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)).save(output/'difference.png')
                result.update(alignment=alignment, alignment_overlay_url=f'/api/batches/{batch_id}/{index}/alignment')
                compatibility = (dict(status='SAME_DESIGN', message='Verified against the active reference PCB.',
                                      alignment_evidence=registration['verification']) if registration else
                                 check_compatibility(reference_layout, inspection_layout, ref_image,
                                                     aligned, mask, homography, rp))
                if compatibility['status'] == 'REVIEW' and not registration:
                    # A four-point warp alone is geometry, not image verification.
                    # Catalog/appearance review may be stale after a local defect.
                    # Verify this supplied transform against distributed features.
                    try:
                        polygon = saved_reference['board_polygon'] if saved_reference else board_polygon(ref_image)
                        features = cached_reference(request.reference_id, json.dumps(polygon))
                        matches = match_surfaces(features, inspection_image)
                        evidence = verify_alignment(ref_image, inspection_image, features, matches, homography, aligned, mask)
                        alignment['verification'] = evidence
                        compatibility = dict(status='SAME_DESIGN', message='Distributed on-board structure verifies the active reference.',
                                             reason='verified_reference_structure', alignment_evidence=evidence,
                                             previous_assessment=compatibility)
                    except (ValueError, cv2.error) as error:
                        compatibility = dict(compatibility, verification_failure=str(error))
                result['board_compatibility'] = compatibility
                if compatibility['status'] != 'SAME_DESIGN':
                    result['reason'] = compatibility.get('verification_failure') or compatibility.get('reason') or compatibility['message']
                    result['component_inspection'].update(status='blocked', reason=result['reason'])
                    results.append(result)
                    continue
                alignment['verification_status'] = 'verified'
                detector_evidence = dict(coordinate_system='decoded_reference_pixels')
                polygon = saved_reference['board_polygon'] if saved_reference else None
                for side in ['reference','inspection']:
                    try:
                        detected = (reference_component_detections(request.reference_id, json.dumps(polygon)) if side == 'reference'
                                    else transform_components(propose_components(inspection_image)['components'],
                                                              homography, ref_image.size))
                        detector_evidence[side] = dict(status='ok', components=detected)
                    except (ValueError, cv2.error) as error:
                        detector_evidence[side] = dict(status='unavailable', reason=str(error), components=[])
                result['component_detection_evidence'] = detector_evidence
                comparison = compare_regions(ref_image, aligned, mask, regions, config, alignment, request.sharpen,
                                             detection_evidence=detector_evidence)
                result['components_evaluated'] = True
                result['component_inspection'].update(status='completed', reason=None, decision_count=len(comparison['components']))
                annotated_overlay(ref_image, aligned, mask, comparison).save(output/'components.png')
                result.update(comparison, photo_id=item.photo_id, filename=current['filename'], alignment=alignment,
                              alignment_overlay_url=f'/api/batches/{batch_id}/{index}/alignment',
                              difference_overlay_url=f'/api/batches/{batch_id}/{index}/difference',
                              component_overlay_url=f'/api/batches/{batch_id}/{index}/components')
            except Exception as error:
                if not isinstance(error, (ValueError, cv2.error)):
                    result['outcome'] = 'error'
                reason = str(error) if isinstance(error, (ValueError, HTTPException)) else f'{type(error).__name__}: {error}'
                if result['alignment']['status'] != 'ok':
                    result['alignment'] = dict(status='failure', reason=reason, verification_status='rejected')
                    result['board_compatibility'] = dict(status='REVIEW', message='Board identity could not be verified.',
                                                        reason=reason, evidence=result.get('board_compatibility'))
                result['reason'] = reason
                result['components_evaluated'] = False
                result['component_inspection'].update(status='error' if result['alignment']['status'] == 'ok' else 'blocked', reason=reason)
                result['components'] = [dict(id=p.get('id'), name=p.get('name'), bbox_xyxy_px=p.get('bbox_xyxy_px'),
                                             status='not_evaluated', display_status='Not evaluated', score=None,
                                             overlap=None, reason=reason) for p in request.components]
            results.append(result)
        for result in results:
            compatibility = result.get('board_compatibility') or {}
            result['alignment_state'] = ('DIFFERENT_BOARD' if compatibility.get('status') == 'DIFFERENT_BOARD'
                else 'ALIGNED' if result['alignment'].get('verification_status') == 'verified'
                else 'ALIGNMENT_FAILED' if result['alignment']['status'] == 'failure'
                else 'NEEDS_REVIEW')
            result['classification'] = ('BOARD_MISMATCH' if compatibility.get('status') == 'DIFFERENT_BOARD'
                else 'NEEDS_REVIEW' if not result['components_evaluated'] or result.get('outcome') == 'review'
                else 'MISALIGNED_COMPONENT' if any(p['status'] == 'misaligned' for p in result['components'])
                else 'MISSING_COMPONENT' if any(p['status'] == 'missing' for p in result['components'])
                else 'GOOD')
        batch = dict(batch_id=batch_id, reference_id=request.reference_id, mode=request.mode,
                     synthetic=request.synthetic, sharpening_enabled=request.sharpen,
                     simulated=request.simulated,
                     annotations=request.model_dump(),
                     thresholds_provisional=True, comparison_config=config, photos=results,
                     report_url=f'/api/batches/{batch_id}/report')
        (batch_path/'report.json').write_text(json.dumps(batch, indent=2, allow_nan=False), encoding='utf-8')
        store.record_batch(batch)
        return batch

    def simulate_image(path, golden=None):
        golden = golden or store.golden()
        if not golden:
            raise ValueError('Save a golden configuration before starting simulation')
        _, reference_path = photo(golden['reference_id'])
        if not (reference_path/'reference.json').is_file():
            raise ValueError('Confirm reference landmarks and outline before starting simulation')
        uploaded = upload(UploadFile(file=path.open('rb'), filename=path.name))
        batch = inspect(InspectionRequest(reference_id=golden['reference_id'], reference_points=[],
                                          inspections=[PhotoPoints(photo_id=uploaded['id'])],
                                          components=golden['components'], mode='automatic',
                                          sharpen=golden.get('sharpen', False), synthetic=False, simulated=True))
        result = batch['photos'][0]
        result['current_image_url'] = uploaded['image_url']
        result['golden_reference_id'] = golden['reference_id']
        return result

    simulator = LineSimulator(simulate_image)
    live_reference = None
    live_reference_lock = threading.Lock()

    def selected_live_reference():
        with live_reference_lock:
            return live_reference or store.golden()

    def live_reference_view(config):
        record, path = photo(config['reference_id'])
        setup = json.loads((path/'reference.json').read_text())
        return dict(config, reference={**record, **setup})

    @app.get('/api/simulation/reference')
    def simulation_reference(authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        config = selected_live_reference()
        if not config:
            raise HTTPException(404, 'Upload a golden reference before starting live inspection')
        return live_reference_view(config)

    @app.post('/api/simulation/reference')
    def upload_simulation_reference(image: UploadFile, authorization: str | None = Header(default=None)):
        nonlocal live_reference
        authorize(authorization, ROLES)
        record = upload(image)
        if record['error']:
            raise HTTPException(422, record['error'])
        automatic_reference_setup(record['id'])
        proposal = component_proposals(record['id'])
        # Publish only complete references; an in-flight frame retains its snapshot.
        config = dict(reference_id=record['id'], components=[dict(p, candidate_status='DETECTED')
                      for p in proposal['components']], mode='automatic', sharpen=False,
                      updated_at=record.get('created_at'), source='live_upload')
        with live_reference_lock:
            live_reference = config
        return live_reference_view(config)

    @app.get('/api/simulation')
    def simulation_status(authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        return simulator.state()

    @app.post('/api/live/frame')
    def camera_frame(image: UploadFile, reference_id: str = Form(),
                     authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        golden = selected_live_reference()
        if not golden or golden['reference_id'] != reference_id:
            raise HTTPException(409, 'Golden reference changed; capture a new frame against the active reference')
        uploaded = upload(image)
        if uploaded['error']:
            raise HTTPException(422, uploaded['error'])
        batch = inspect(InspectionRequest(reference_id=golden['reference_id'],
            components=golden['components'], mode='automatic', sharpen=golden.get('sharpen', False),
            inspections=[PhotoPoints(photo_id=uploaded['id'])], simulated=False))
        return dict(batch['photos'][0], golden_reference_id=golden['reference_id'],
                    report_url=batch['report_url'])

    @app.post('/api/simulation/import')
    def simulation_import(images: list[UploadFile], queue_id: str | None = Form(default=None),
                          relative_paths: list[str] = Form(default=[]),
                          authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        if not 1 <= len(images) <= MAX_PHOTOS:
            raise HTTPException(422, f'Upload chunks must contain between 1 and {MAX_PHOTOS} images')
        if relative_paths and len(relative_paths) != len(images):
            raise HTTPException(422, 'relative_paths must match the uploaded image count')
        if queue_id:
            if not re.fullmatch(r'[0-9a-f]{32}', queue_id):
                raise HTTPException(422, 'Invalid import queue id')
            import_path = storage/'imports'/queue_id
            if not import_path.is_dir():
                raise HTTPException(404, 'Import queue does not exist')
        else:
            queue_id = uuid.uuid4().hex
            import_path = storage/'imports'/queue_id
            import_path.mkdir(parents=True)
        existing = len(list(import_path.rglob('*.png')))
        if existing + len(images) > 1000:
            raise HTTPException(422, 'An import queue can contain at most 1000 images')
        imported, skipped = [], []
        for index, image in enumerate(images):
            record = upload(image)
            if record['error']:
                skipped.append({'filename': record['filename'], 'reason': record['error']})
                continue
            _, source = photo(record['id'])
            raw_relative = relative_paths[index] if relative_paths else record['filename']
            parts = raw_relative.replace('\\', '/').split('/')
            if not parts or any(part in {'', '.', '..'} for part in parts):
                skipped.append({'filename': record['filename'], 'reason': 'Invalid nested-folder relative path'})
                continue
            clean_parts = [re.sub(r'[^A-Za-z0-9_.-]+', '-', part)[:80] or 'item' for part in parts]
            relative = Path(*clean_parts[:-1])/(Path(clean_parts[-1]).stem + '.png')
            target = import_path/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            suffix = 1
            while target.exists():
                target = target.with_name(f'{target.stem}-{suffix}.png')
                suffix += 1
            read_image(source/'image.png').save(target)
            imported.append({'filename': record['filename'], 'relative_path': target.relative_to(import_path).as_posix()})
        total = len(list(import_path.rglob('*.png')))
        return {'queue_id': queue_id, 'dataset_directory': str(import_path.resolve()), 'count': total,
                'total_count': total, 'accepted_count': len(imported), 'skipped_count': len(skipped),
                'accepted': imported, 'skipped': skipped}

    @app.post('/api/simulation/start')
    def simulation_start(request: SimulationStart, authorization: str | None = Header(default=None)):
        authorize(authorization, {'administrator', 'supervisor', 'operator'})
        golden = selected_live_reference()
        if not golden:
            raise HTTPException(422, 'Upload a golden reference or save a golden configuration before starting simulation')
        try:
            return simulator.start(
                request.dataset_directory, request.interval,
                process_image=lambda path: simulate_image(path, selected_live_reference()),
                metadata={'golden_reference_id': golden['reference_id'],
                          'golden_updated_at': golden['updated_at'], 'simulated': True},
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error

    @app.post('/api/simulation/{action}')
    def simulation_control(action: Literal['pause', 'resume', 'stop'],
                           authorization: str | None = Header(default=None)):
        authorize(authorization, ROLES)
        try:
            return getattr(simulator, action)()
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error

    @app.get('/api/batches/{identifier}/report')
    def report(identifier: str):
        return FileResponse(directory('batches', identifier)/'report.json', media_type='application/json')

    @app.get('/api/batches/{identifier}/{index}/{kind}')
    def result_asset(identifier: str, index: int, kind: str):
        if index not in range(MAX_PHOTOS) or kind not in ['alignment', 'components', 'difference']:
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


app = create_app(os.environ.get('PCB_WEB_STORAGE'))
