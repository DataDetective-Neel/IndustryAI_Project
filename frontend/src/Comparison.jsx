import React, { useState } from 'react';
import { findingBox, homographyTransform } from './comparison.js';
import Landmarks from './Landmarks.jsx';

const outcomes = {
  ok: 'Scored regions present', defect: 'Suspected defect', missing: 'Missing component', review: 'Needs review',
  retake: 'Alignment needs review', error: 'Photo could not be processed',
  DIFFERENT_BOARD: 'Different board', different_board: 'Different board',
};

export default function Comparison({ result, reference, inspection, index, mode, onManual }) {
  const [view, setView] = useState('side');
  const [opacity, setOpacity] = useState(0.5);
  const [selected, setSelected] = useState(null);
  const transform = result.alignment?.status === 'ok'
    ? homographyTransform(result.alignment.homography_inspection_to_reference) : null;
  const canOverlay = !!(transform && reference?.image_url && inspection?.image_url);
  const canDifference = !!result.difference_overlay_url;
  const overlay = view === 'overlay' && canOverlay;
  const parts = result.components || [];
  const defects = parts.filter(p => ['missing', 'misaligned'].includes(p.status));
  const part = parts[selected];
  const box = findingBox(part?.bbox_xyxy_px, reference?.width, reference?.height);
  const outcome = result.board_compatibility?.status === 'DIFFERENT_BOARD' ? 'DIFFERENT_BOARD' : result.outcome;
  const identityBlocked = result.components_evaluated === false && result.alignment?.status === 'ok';
  const failed = result.alignment?.status !== 'ok';
  const verified = result.alignment?.verification_status === 'verified';
  const inspectionPoints = result.alignment?.inspection_points || [];
  const referencePoints = result.alignment?.reference_points || reference?.points || [];
  const unreliable = result.alignment_validation?.reliable === false;
  return <article className="result-sheet" data-testid={`result-${index}`}>
    <div className="result-heading">
      <h3>{result.filename}</h3>
      <strong className={`status ${outcome}`}>{identityBlocked ? 'Inspection blocked' : outcomes[outcome] || outcome || 'Outcome unavailable'}</strong>
    </div>
    <div className="registration-status" role="status">
      <strong>Registration: {failed ? 'Needs review' : verified ? 'Verified' : 'Geometry valid; image verification pending'}</strong>
      {result.alignment?.verification && <span>
        {result.alignment.verification.inliers} inliers · median error {result.alignment.verification.median_error_px.toFixed(3)} px · board overlap {(100 * result.alignment.verification.board_overlap).toFixed(1)}%
      </span>}
    </div>
    <details className="registration-diagnostics"><summary>Registration diagnostics</summary>
      <pre>{JSON.stringify({ alignment: result.alignment, landmarks: result.landmark_diagnostics }, null, 2)}</pre>
    </details>
    {result.alignment?.source && <p className="alignment-summary">Landmarks: {result.alignment.source === 'reference_registration' ? 'Registration-derived' : result.alignment.source === 'manual_landmarks' ? 'Manual corrections' : 'Model-detected'} · {verified ? 'verified correspondence' : 'tentative correspondence'}</p>}
    <p className="alignment-summary">Board identity: {result.board_compatibility?.status || 'Not evaluated'} · Component inspection: {result.component_inspection?.status || (result.components_evaluated ? 'completed' : 'not attempted')}</p>
    {result.reason && <p className="result-reason">{result.reason}</p>}
    {result.board_compatibility && <details>
      <summary>Board compatibility evidence</summary>
      <pre style={{whiteSpace:'pre-wrap', overflowWrap:'anywhere'}}>{JSON.stringify(result.board_compatibility, null, 2)}</pre>
    </details>}
    {(failed || unreliable) && <div className="message notice" role="status">
      <strong>{failed ? 'Component scoring skipped.' : 'Alignment needs review.'}</strong>
      <span>{result.alignment?.reason || 'Correct the mounting holes or retake the photo before trusting component scores.'}</span>
      {mode === 'automatic' && outcome !== 'DIFFERENT_BOARD' && <button className="secondary" onClick={onManual}>Switch to Manual</button>}
    </div>}
    {result.components_evaluated === false && !failed && <div className="message notice">Component scoring blocked: {result.component_inspection?.reason || result.reason || result.board_compatibility?.reason || 'Board identity needs verification.'}</div>}
    {result.alignment_validation && <p className="alignment-summary">Alignment overlay score: {result.alignment_validation.overlay_score?.toFixed(4) ?? 'unavailable'}; {result.alignment_validation.reliable ? 'validated' : 'REVIEW — correct landmarks or retake photo'}</p>}
    <div className="comparison-toolbar">
      <div className="tool-switch" aria-label={`Comparison view for ${result.filename}`}>
        <button aria-pressed={view === 'side'} onClick={() => setView('side')}>Side by side</button>
        <button aria-pressed={view === 'reference'} onClick={() => setView('reference')}>Reference</button>
        <button aria-pressed={view === 'inspection'} disabled={!inspection?.image_url} onClick={() => setView('inspection')}>Inspection</button>
        <button aria-pressed={overlay} disabled={!canOverlay} onClick={() => setView('overlay')}>Overlay</button>
        <button aria-pressed={view === 'difference'} disabled={!canDifference} onClick={() => setView('difference')}>Difference</button>
      </div>
      {overlay ? <label className="opacity-control">Inspection opacity
        <input aria-label={`Inspection opacity for ${result.filename}`} type="range" min="0" max="100" value={Math.round(opacity * 100)} onChange={(e) => setOpacity(Number(e.target.value) / 100)} />
        <output>{Math.round(opacity * 100)}%</output>
      </label> : <span className="muted">{canOverlay ? 'Original photos · Overlay uses aligned inspection' : 'Original photos · Aligned overlay unavailable'}</span>}
    </div>
    <div className="comparison-layout">
      <div className={`comparison-images ${overlay ? 'overlay-view' : ''}`}>
        {view !== 'inspection' && view !== 'difference' && <figure>
          <figcaption>{overlay ? 'Aligned comparison' : 'Known-good reference'}</figcaption>
          {reference?.image_url && <svg className="comparison-canvas" role="img" aria-label={`${overlay ? 'Aligned comparison' : 'Reference comparison'} for ${result.filename}`} viewBox={`0 0 ${reference.width} ${reference.height}`}>
            <image href={reference.image_url} width={reference.width} height={reference.height} />
            {overlay && <foreignObject x="0" y="0" width={reference.width} height={reference.height}>
              <div style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
                <img alt="Aligned inspection" src={inspection.image_url} style={{ width: inspection.width, height: inspection.height, maxWidth: 'none', transform, transformOrigin: '0 0', opacity, display: 'block' }} />
              </div>
            </foreignObject>}
            <Landmarks points={referencePoints} width={reference.width} height={reference.height} verified={verified}/>
            {box && !defects.some(p => p.id === part.id) && <rect className={`finding-highlight ${part.status}`} x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} vectorEffect="non-scaling-stroke" />}
            {defects.map(p => { const b = findingBox(p.bbox_xyxy_px, reference.width, reference.height); return b && <rect key={p.id} className={`finding-highlight ${p.status}`} x={b[0]} y={b[1]} width={b[2]-b[0]} height={b[3]-b[1]} vectorEffect="non-scaling-stroke"><title>{p.id}: {p.display_status}</title></rect>; })}
          </svg>}
        </figure>}
        {(view === 'side' || view === 'inspection') && <figure>
          <figcaption>{view === 'side' && canOverlay ? 'Registered inspection' : 'Inspection'} · {result.filename}</figcaption>
          {view === 'side' && canOverlay ? <svg className="comparison-canvas" role="img" aria-label={`Registered findings for ${result.filename}`} viewBox={`0 0 ${reference.width} ${reference.height}`}>
            <foreignObject x="0" y="0" width={reference.width} height={reference.height}>
              <div style={{width:'100%',height:'100%',overflow:'hidden'}}>
                <img alt="Registered inspection" src={inspection.image_url} style={{width:inspection.width,height:inspection.height,maxWidth:'none',transform,transformOrigin:'0 0',display:'block'}} />
              </div>
            </foreignObject>
            <Landmarks points={referencePoints} width={reference.width} height={reference.height} verified={verified}/>
            {defects.map(p => { const b = findingBox(p.bbox_xyxy_px, reference.width, reference.height); return b && <rect key={p.id} className={`finding-highlight ${p.status}`} x={b[0]} y={b[1]} width={b[2]-b[0]} height={b[3]-b[1]} vectorEffect="non-scaling-stroke"><title>{p.id}: {p.display_status}</title></rect>; })}
          </svg> : inspection?.image_url ? <svg className="comparison-canvas" role="img" aria-label={`Inspection original for ${result.filename}`} viewBox={`0 0 ${inspection.width} ${inspection.height}`}>
            <image href={inspection.image_url} width={inspection.width} height={inspection.height}/>
            <Landmarks points={inspectionPoints} width={inspection.width} height={inspection.height} verified={verified}/>
          </svg> : <p className="message notice">Inspection photo unavailable. Replace the photo and retry.</p>}
        </figure>}
        {view === 'difference' && <figure><figcaption>Structural difference heatmap</figcaption>
          <img className="inspection-original" src={result.difference_overlay_url} alt={`Difference heatmap for ${result.filename}`} />
        </figure>}
      </div>
      <aside className="findings-panel" aria-label={`Findings for ${result.filename}`}>
        <h3>Findings <span className="muted">{parts.filter(p=>p.status!=='not_evaluated').length} decisions · {defects.length} defects</span></h3>
        {!parts.length && <p className="muted">No component decisions returned. {result.reason || 'Review the alignment and board compatibility above.'}</p>}
        {parts.map((p, i) => <div className={`finding ${selected === i ? 'active-finding' : ''}`} key={`${p.id}-${i}`}>
          <button className="finding-select" aria-pressed={selected === i} onClick={() => setSelected(selected === i ? null : i)}>
            <span>{p.name}</span><span className={`status ${p.status}`}>{p.display_status || p.status}</span>
          </button>
          <p>{p.reason?.replace(/^explicit_review: /, '').replaceAll('_', ' ')}</p>
          <details><summary>Measurement details</summary>
            <dl>
              <dt>Component ID</dt><dd>{p.id}</dd>
              <dt>Decision</dt><dd>{p.decision || p.display_status || p.status}</dd>
              <dt>Detection confidence</dt><dd>{p.detector_evidence?.inspection?.confidence == null ? '—' : p.detector_evidence.inspection.confidence.toFixed(3)}</dd>
              <dt>Similarity</dt><dd>{p.score == null ? '—' : p.score.toFixed(6)}</dd>
              <dt>Best offset (px)</dt><dd>{p.best_match_offset_px?.join(', ') || '—'}</dd>
              <dt>Rotation after registration</dt><dd>{p.evidence?.rotation_deg == null ? '—' : `${p.evidence.rotation_deg.toFixed(1)}°`}</dd>
              <dt>Displacement magnitude</dt><dd>{p.evidence?.displacement_magnitude_px == null ? '—' : `${p.evidence.displacement_magnitude_px.toFixed(2)} px`}</dd>
              <dt>Expected box</dt><dd>{p.bbox_xyxy_px?.join(', ') || '—'}</dd>
              <dt>Observed box</dt><dd>{p.observed_location?.join(', ') || '—'}</dd>
              <dt>Shift tolerance</dt><dd>{p.evidence?.displacement_tolerance_px == null ? '—' : `${p.evidence.displacement_tolerance_px.toFixed(2)} px`}</dd>
              <dt>Coverage</dt><dd>{p.overlap == null ? '—' : `${(p.overlap * 100).toFixed(2)}%`}</dd>
              <dt>Edge energy ratio</dt><dd>{p.evidence?.edge_energy_ratio == null ? '—' : p.evidence.edge_energy_ratio.toFixed(4)}</dd>
              <dt>LAB difference</dt><dd>{p.evidence?.mean_lab_delta == null ? '—' : p.evidence.mean_lab_delta.toFixed(4)}</dd>
            </dl>
          </details>
          {selected === i && <small>{box ? 'Highlighted on the reference.' : 'No valid region coordinates returned.'}</small>}
        </div>)}
      </aside>
    </div>
    <div className="evidence-links">
      {result.alignment_overlay_url && <a href={result.alignment_overlay_url} target="_blank" rel="noreferrer">Alignment overlay</a>}
      {result.component_overlay_url && <a href={result.component_overlay_url} target="_blank" rel="noreferrer">Component decisions</a>}
    </div>
  </article>;
}
