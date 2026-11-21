"""Reproduce the one-board demo through the real upload/landmark/inspection routes.

Run: .venv/Scripts/python -m pcb_landmarks.demo_check
Generated warps and erasures are demo fixtures, never real defect evidence.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from .align import align_images, label_points
from .data import read_image
from .web import CHECKPOINT, ROOT, _detector, create_app


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    client = TestClient(create_app(output/'app'))
    preset = json.loads((ROOT/'configs/components-ECCC5.json').read_text())
    reference = np.array(read_image(ROOT/preset['reference_image']))
    h,w = reference.shape[:2]
    rp = label_points(ROOT/'PCB_Dataset_Pilot/labels/val/ECCC5.txt', (w,h))
    corners = np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]])
    forward = cv2.getPerspectiveTransform(corners,np.float32([[24,30],[w-40,9],[w-12,h-25],[40,h-8]]))
    warped = cv2.warpPerspective(reference,forward,(w,h))
    ip = cv2.perspectiveTransform(rp[None],forward)[0]
    (output/'transform.json').write_text(json.dumps(dict(synthetic=True,reference_to_inspection=forward.tolist(),inspection_to_reference=np.linalg.inv(forward).tolist()),indent=2))
    Image.fromarray(reference).save(output/'reference.png')
    Image.fromarray(warped).save(output/'mild-perspective.png')
    cropped = reference[:,w//2:].copy()
    Image.fromarray(cropped).save(output/'badly-cropped.png')
    defect=reference.copy(); defect[440:545,380:480]=(35,45,38)
    Image.fromarray(defect).save(output/'SIMULATED-erasure.png')
    detector,config=_detector(str(CHECKPOINT.resolve()))
    evidence=dict(checkpoint_path=str(CHECKPOINT.resolve()),checkpoint_present=CHECKPOINT.is_file(),checkpoint_loadable=True,
                  checkpoint_sha256=detector.sha256,checkpoint_schema=dict(task=detector.model.task,names=detector.model.names,kpt_shape=detector.model.model.yaml['kpt_shape']),
                  cases={},direct_vs_app={},synthetic_defect=True,real_missing_example=None)

    def upload(array,name):
        stream=io.BytesIO(); Image.fromarray(array).save(stream,format='PNG')
        response=client.post('/api/photos',files={'image':(name,stream.getvalue(),'image/png')})
        response.raise_for_status();record=response.json(); assert not record['error'],record
        return record

    ref=upload(reference,'ECCC5.jpg')
    saved=client.get(f"/api/photos/{ref['id']}/regions");saved.raise_for_status()
    assert saved.json()['components']==preset['components']

    def diagnostics(record,array,manual,label):
        path=output/'app/photos'/record['id']/'image.png'
        direct=detector.predict(path,config['board_conf'],config['point_conf'])
        response=client.post(f"/api/landmarks/{record['id']}");response.raise_for_status();api=response.json()
        assert direct==api, 'Direct and app inference differ'
        overlay=Image.fromarray(array);draw=ImageDraw.Draw(overlay)
        errors=[]
        for index,point in enumerate(manual):
            x,y=point; draw.ellipse((x-10,y-10,x+10,y+10),outline='lime',width=3); draw.text((x+12,y),f'L{index} labeled',fill='lime')
        for candidate in direct['diagnostics']['candidates']:
            for point in candidate['landmarks']:
                x,y=point['x'],point['y']
                draw.ellipse((x-10,y-10,x+10,y+10),outline='red',width=3)
                draw.text((x+12,y),f"L{point['id']} raw {point['confidence']:.3f}",fill='red')
                errors.append(float(np.linalg.norm(np.array([x,y])-manual[point['id']])))
        overlay.save(output/f'{label}-landmarks.png')
        evidence['direct_vs_app'][label]=dict(equal=True,decoded_raster_sha256=hashlib.sha256(array.tobytes()).hexdigest(),
            labeled_points_px=manual.tolist(),landmark_error_px=errors,app=api)
        return direct

    altered=reference.copy(); altered[0,0] ^= 255
    mismatch=upload(altered,'ECCC5.jpg')
    assert client.get(f"/api/photos/{mismatch['id']}/regions").status_code==404
    ref_detection=diagnostics(ref,reference,rp,'reference')
    evidence['matching_existing_app_uploads'] = []
    for record_path in (ROOT/'runs/web/photos').glob('*/photo.json'):
        record = json.loads(record_path.read_text())
        raster = record_path.parent/'image.png'
        if record.get('filename') == 'ECCC5.jpg' and raster.is_file() and np.array_equal(np.array(read_image(raster)), reference):
            evidence['matching_existing_app_uploads'].append(record['id'])
    samples=[('identical',reference,rp,False),('mild_perspective',warped,ip,True),('badly_cropped',cropped,rp-np.array([w//2,0]),True),('SIMULATED_erasure',defect,rp,True)]
    for name,image,points,synthetic in samples:
        record=upload(image,name+'.png')
        diagnostics(record,image,points,name)
        for mode in ['manual','automatic']:
            payload=dict(reference_id=ref['id'],reference_points=rp.tolist(),inspections=[dict(photo_id=record['id'],points=points.tolist())],
                         components=preset['components'],mode=mode,synthetic=synthetic)
            response=client.post('/api/inspections',json=payload);response.raise_for_status();batch=response.json();result=batch['photos'][0]
            case=dict(outcome=result['outcome'],statuses={p['id']:p['status'] for p in result['components']},
                      missing_count=sum(p['status']=='missing' for p in result['components']),
                      alignment_validation=result.get('alignment_validation'),alignment=result['alignment'],
                      report_url=batch['report_url'],synthetic=synthetic)
            evidence['cases'][name+'_'+mode]=case
            (output/f'{name}-{mode}-report.json').write_text(json.dumps(batch,indent=2))
            for kind in ['alignment','component']:
                url=result.get(kind+'_overlay_url')
                if url:
                    (output/f'{name}-{mode}-{kind}.png').write_bytes(client.get(url).content)
            if mode=='manual' and name in ['identical','mild_perspective']:
                assert all(p['status']=='present' for p in result['components']),case
            elif mode=='manual' and name=='SIMULATED_erasure':
                assert result['outcome']=='review' and sum(p['status']=='present' for p in result['components'])==7,case
                assert result['components'][0]['status']=='uncertain',case
            elif mode=='automatic' or name=='badly_cropped':
                assert result['outcome']=='review',case
            assert case['missing_count']==0,case
    # Feature locations beyond the four fitted landmarks, tested against the saved transform.
    features=np.array([[(b[0]+b[2])/2,(b[1]+b[3])/2] for b in [p['bbox_xyxy_px'] for p in preset['components']]],dtype=np.float64)
    inspection_features=cv2.perspectiveTransform(features[None],forward)[0]
    _,manual_h,_=align_images(reference,warped,rp,ip)
    errors=np.linalg.norm(cv2.perspectiveTransform(inspection_features[None],manual_h)[0]-features,axis=1)
    mild_report=json.loads((output/'mild_perspective-manual-report.json').read_text())['photos'][0]
    evidence['beyond_landmarks']=dict(local_match_offsets_px={p['id']:p['best_match_offset_px'] for p in mild_report['components']},method='eight component centers, known saved perspective matrix',manual_error_px=errors.tolist(),manual_max_error_px=float(errors.max()))
    assert errors.max()<.01
    candidate=ref_detection['diagnostics']['candidates'][0]['landmarks']
    warped_candidate=evidence['direct_vs_app']['mild_perspective']['app']['diagnostics']['candidates']
    if warped_candidate:
        a=np.array([[p['x'],p['y']] for p in candidate],np.float32)
        b=np.array([[p['x'],p['y']] for p in warped_candidate[0]['landmarks']],np.float32)
        tentative=cv2.getPerspectiveTransform(b,a)
        err=np.linalg.norm(cv2.perspectiveTransform(inspection_features[None],tentative)[0]-features,axis=1)
        evidence['beyond_landmarks']['rejected_raw_hypothetical_error_px']=err.tolist()
    # Diagnose the existing differently angled real photo too; not a synthetic intact-pair claim.
    other=np.array(read_image(ROOT/'PCB_Dataset_Pilot/images/val/ECCB5.jpg'))
    other_points=label_points(ROOT/'PCB_Dataset_Pilot/labels/val/ECCB5.txt',(other.shape[1],other.shape[0]))
    diagnostics(upload(other,'ECCB5.jpg'),other,other_points,'real_angle_ECCB5')
    (output/'evidence.json').write_text(json.dumps(evidence,indent=2,allow_nan=False))
    print(json.dumps(dict(output=str(output.resolve()),cases=evidence['cases'],beyond_landmarks=evidence['beyond_landmarks']),indent=2))
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='runs/demo-evidence')
    run(parser.parse_args().output)
