import React, { useState } from 'react';
import { findingBox, homographyTransform } from './comparison.js';

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
  const part = parts[selected];
  const box = findingBox(part?.bbox_xyxy_px, reference?.width, reference?.height);
  const outcome = result.board_compatibility?.status === 'DIFFERENT_BOARD' ? 'DIFFERENT_BOARD' : result.outcome;
  const alignmentReview = outcome === 'review' && result.components_evaluated === false;
  const failed = result.alignment?.status !== 'ok';
  const unreliable = result.alignment_validation?.reliable === false;
  return <article className="result-sheet" data-testid={`result-${index}`}>
    <div className="result-heading">
      <h3>{result.filename}</h3>
      <strong className={`status ${outcome}`}>{alignmentReview ? 'Needs alignment review' : outcomes[outcome] || outcome || 'Outcome unavailable'}</strong>
    </div>
    {result.alignment?.source && <p className="alignment-summary">Alignment: {result.alignment.source === 'reference_registration' ? 'Reference registration · landmarks projected from confirmed reference' : 'YOLO landmarks verified against reference'}</p>}
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
    {result.components_evaluated === false && !failed && <div className="message notice">Component scoring skipped. {result.board_compatibility?.message || 'Board compatibility needs review.'}</div>}
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
            {box && <rect className={`finding-highlight ${part.status}`} x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]} vectorEffect="non-scaling-stroke" />}
          </svg>}
        </figure>}
        {(view === 'side' || view === 'inspection') && <figure>
          <figcaption>Inspection · {result.filename}</figcaption>
          {inspection?.image_url ? <img className="inspection-original" src={inspection.image_url} alt={`Inspection original for ${result.filename}`} /> : <p className="message notice">Inspection photo unavailable. Replace the photo and retry.</p>}
        </figure>}
        {view === 'difference' && <figure><figcaption>Structural difference heatmap</figcaption>
          <img className="inspection-original" src={result.difference_overlay_url} alt={`Difference heatmap for ${result.filename}`} />
        </figure>}
      </div>
      <aside className="findings-panel" aria-label={`Findings for ${result.filename}`}>
        <h3>Findings <span className="muted">{parts.length}</span></h3>
        {!parts.length && <p className="muted">No component decisions returned. {result.reason || 'Review the alignment and board compatibility above.'}</p>}
        {parts.map((p, i) => <div className={`finding ${selected === i ? 'active-finding' : ''}`} key={`${p.id}-${i}`}>
          <button className="finding-select" aria-pressed={selected === i} onClick={() => setSelected(selected === i ? null : i)}>
            <span>{p.name}</span><span className={`status ${p.status}`}>{p.display_status || p.status}</span>
          </button>
          <p>{p.reason?.replace(/^explicit_review: /, '').replaceAll('_', ' ')}</p>
          <details><summary>Measurement details</summary>
            <dl>
              <dt>Similarity</dt><dd>{p.score == null ? '—' : p.score.toFixed(6)}</dd>
              <dt>Best offset (px)</dt><dd>{p.best_match_offset_px?.join(', ') || '—'}</dd>
              <dt>Expected box</dt><dd>{p.bbox_xyxy_px?.join(', ') || '—'}</dd>
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
