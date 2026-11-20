"""CPU development-only trace; leaves the normal failure contract unchanged."""
import json
import itertools
from pathlib import Path
import numpy as np
from .infer import LandmarkDetector, assess
from .evaluate import collect, summarize, save_samples
from .data import read_image

def main():
    config=json.loads(Path('configs/landmarks.json').read_text())
    model=LandmarkDetector('runs/landmarks/full/weights/best.pt',device='cpu',expected_sha256=config['checkpoint_sha256'])
    records=collect(model,'PCB_Dataset_Pilot/dataset.yaml','val')
    report={'checkpoint_sha256':model.sha256,'device':'cpu','images':[],'thresholds':[]}
    for row in records:
        direct=model.model.predict(str(row['source']),imgsz=640,device='cpu',conf=.001,max_det=20,verbose=False)[0]
        candidates=[]
        for i,(box,score,points) in enumerate(zip(row['boxes'],row['scores'],row['points'])):
            errors=np.linalg.norm(points[:,:2]-row['gt_points'][:,:2],axis=1)
            permutation=min(itertools.permutations(range(4)),key=lambda p:np.linalg.norm(points[list(p),:2]-row['gt_points'][:,:2],axis=1).mean())
            candidates.append(dict(class_id=int(direct.boxes.cls[i]),box=box.tolist(),score=float(score),points=[dict(name=n,x=float(p[0]),y=float(p[1]),confidence=float(p[2])) for n,p in zip(model.names,points)],errors_px=errors.tolist(),best_permutation=list(permutation),best_permutation_mean_error=float(np.linalg.norm(points[list(permutation),:2]-row['gt_points'][:,:2],axis=1).mean())))
        actual=model.predict(row['source'],config['board_conf'],config['point_conf'])
        report['images'].append(dict(image=row['image'],first_rejection=actual['reason'],candidates=candidates,path_vs_pil_max_coordinate_difference=float(np.max(np.abs(direct.keypoints.data.cpu().numpy()-row['points'])))))
        save_samples([row],summarize([row],model.names,.95,.99,.01),'runs/diagnosis/overlays')
    for board in [.25,.5,.75,.9,.95]:
        for point in [.01,.05,.1,.25,.5,.7,.85,.95,.99]:
            s=summarize(records,model.names,board,point,.01)
            report['thresholds'].append(dict(board=board,point=point,accepted=s['all_four_usable'],accurate=s['all_four_within_tolerance'],inaccurate=s['confident_but_inaccurate'],rejected=s['failed_detections']))
    Path('docs/diagnosis').mkdir(exist_ok=True)
    Path('docs/diagnosis/cpu_trace.json').write_text(json.dumps(report,indent=2)+'\n')
    print([(r['image'],r['first_rejection'],r['candidates'][0]['score'],r['candidates'][0]['errors_px']) for r in report['images']])
    assert all(r['first_rejection']=='no_confident_board' for r in report['images'])
    assert all(r['path_vs_pil_max_coordinate_difference']<.01 for r in report['images'])

if __name__=='__main__':
    main()
