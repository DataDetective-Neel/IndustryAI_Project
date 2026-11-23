import React, { useEffect, useRef, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { jsonBody, platformApi } from "../platformApi.js";
import Pagination, { usePage } from "../components/Pagination.jsx";

export default function LiveInspection({ user }) {
  const [line, setLine] = useState({ status: "stopped", processed: 0, passed: 0, alarms: 0, errors: 0 });
  const [reviews, setReviews] = useState([]), [directory, setDirectory] = useState("");
  const [history, setHistory] = useState([]), [imported, setImported] = useState(null);
  const [interval, setIntervalValue] = useState(user.preferences.inspection_interval ?? 3), [error, setError] = useState("");
  const [deciding, setDeciding] = useState(null);
  const [golden, setGolden] = useState(null), [uploadingGolden, setUploadingGolden] = useState(false);
  const [goldens, setGoldens] = useState([]);
  const reviewsPage = usePage(reviews), historyPage = usePage(history);
  const [camera, setCamera] = useState(false), [startingCamera, setStartingCamera] = useState(false);
  const [cameraResult, setCameraResult] = useState(null);
  const video = useRef(null), stream = useRef(null), cameraGeneration = useRef(0);
  const cameraBusy = useRef(false), cameraSettings = useRef({});
  const goldenRevision = useRef(0), goldenUploadPending = useRef(false);
  cameraSettings.current = { golden, uploadingGolden, interval };
  const alarmCount = useRef(0), alarmReady = useRef(false);
  const refresh = () => {
    const revision = goldenRevision.current;
    return Promise.all([platformApi("/api/simulation"), platformApi("/api/reviews"), platformApi("/api/dashboard"), platformApi('/api/simulation/reference').catch(() => null), platformApi('/api/golden-library').catch(() => ({references:[]}))])
      .then(([state, pending, dashboard, selectedGolden, library]) => { setLine(state); setReviews(pending.reviews); setHistory(dashboard.recent_inspections); setGoldens(library.references);
        if (revision === goldenRevision.current && !goldenUploadPending.current) setGolden(selectedGolden);
      }).catch(error => setError(error.message));
  };
  useEffect(() => { refresh(); const timer = setInterval(refresh, 1200); return () => clearInterval(timer); }, []);
  async function uploadGolden(event) {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    cameraGeneration.current += 1; setCameraResult(null);
    goldenRevision.current += 1; goldenUploadPending.current = true;
    setUploadingGolden(true); setError('');
    try {
      const body = new FormData(); body.append('image', file);
      const selected = await platformApi('/api/simulation/reference', {method:'POST', body});
      setGolden(selected);
      const name = window.prompt('Name this golden PCB to save it in the library:', file.name.replace(/\.[^.]+$/, ''));
      if (name?.trim()) {
        try { await platformApi('/api/golden-library', jsonBody({reference_id:selected.reference_id,name:name.trim()})); }
        catch (e) { setError(`Golden reference is active but was not saved to the library: ${e.message}`); }
      }
      await refresh();
    } catch(e) { setError(`Golden reference processing failed: ${e.message}`); }
    finally { goldenRevision.current += 1; goldenUploadPending.current = false; setUploadingGolden(false); }
  }
  async function selectGolden(event) {
    const id = event.target.value; if (!id) return;
    goldenRevision.current += 1; goldenUploadPending.current = true; setUploadingGolden(true);
    try { setGolden(await platformApi(`/api/simulation/reference/${id}`, {method:'PUT'})); setError(''); }
    catch (e) { setError(e.message); }
    finally { goldenRevision.current += 1; goldenUploadPending.current = false; setUploadingGolden(false); }
  }
  useEffect(() => {
    if (alarmReady.current && line.alarms > alarmCount.current && user.preferences.alarm_sound !== false && localStorage.getItem("aoi_alarm_sound") !== "false") {
      try { const audio = new AudioContext(); const oscillator = audio.createOscillator(); oscillator.frequency.value = 880; oscillator.connect(audio.destination); oscillator.start(); oscillator.stop(audio.currentTime + .18); } catch {}
    }
    alarmReady.current = true; alarmCount.current = line.alarms;
  }, [line.alarms, user.preferences.alarm_sound]);
  async function importFiles(event) { const files = [...event.target.files]; event.target.value = ""; if (!files.length) return;
    try { setError(""); let queueId = null, accepted = 0; const skipped = [];
      for (let offset = 0; offset < files.length; offset += 15) {
        const body = new FormData();
        files.slice(offset, offset + 15).forEach(file => {
          body.append("images", file);
          body.append("relative_paths", file.webkitRelativePath || file.name);
        });
        if (queueId) body.append("queue_id", queueId);
        const result = await platformApi("/api/simulation/import", { method: "POST", body });
        queueId = result.queue_id; accepted += result.accepted_count; skipped.push(...result.skipped);
        setDirectory(result.dataset_directory);
      }
      setImported({ accepted, skipped });
    } catch (e) { setError(e.message); } }
  async function start() { try { setError(""); setLine(await platformApi("/api/simulation/start", jsonBody({ dataset_directory: directory, interval: Number(interval) }))); } catch (e) { setError(e.message); } }
  async function control(action) { try { setError(""); setLine(await platformApi(`/api/simulation/${action}`, { method: "POST" })); } catch (e) { setError(e.message); } }
  async function decide(id, decision) { if (deciding) return; setDeciding(id); try { await platformApi(`/api/reviews/${encodeURIComponent(id)}/decision`, jsonBody({ decision, note: "Decision recorded in live console" })); await refresh(); } catch (e) { setError(e.message); } finally { setDeciding(null); } }
  function stopCamera() {
    cameraGeneration.current += 1;
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null;
    setCamera(false); setCameraResult(null);
  }
  async function startCamera() {
    const generation = ++cameraGeneration.current;
    setStartingCamera(true); setCameraResult(null); setError('');
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires localhost and a supported browser.');
      const acquired = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
      if (generation !== cameraGeneration.current) { acquired.getTracks().forEach(track => track.stop()); return; }
      stream.current = acquired; setCamera(true);
    } catch (e) { setError(`Camera unavailable: ${e.message}`); }
    finally { setStartingCamera(false); }
  }
  useEffect(() => () => {
    cameraGeneration.current += 1;
    stream.current?.getTracks().forEach(track => track.stop());
  }, []);
  useEffect(() => { cameraGeneration.current += 1; setCameraResult(null); }, [golden?.reference_id]);
  useEffect(() => {
    if (!camera) return;
    let stopped = false, timer;
    const player = video.current;
    player.srcObject = stream.current;
    async function capture() {
      const settings = cameraSettings.current;
      const generation = cameraGeneration.current;
      let ownsRequest = false;
      try {
        if (cameraBusy.current || settings.uploadingGolden || !settings.golden || !player.videoWidth) return;
        cameraBusy.current = true; ownsRequest = true;
        const canvas = document.createElement('canvas');
        canvas.width = player.videoWidth; canvas.height = player.videoHeight;
        canvas.getContext('2d').drawImage(player, 0, 0);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
        if (!blob) throw new Error('Camera frame could not be encoded');
        const body = new FormData(); body.append('image', blob, 'camera.png');
        body.append('reference_id', settings.golden.reference_id);
        const result = await platformApi('/api/live/frame', { method: 'POST', body });
        if (!stopped && generation === cameraGeneration.current &&
            result.golden_reference_id === cameraSettings.current.golden?.reference_id) {
          setCameraResult(result); setError(''); refresh();
        }
      } catch (e) {
        if (!stopped && generation === cameraGeneration.current) { setCameraResult(null); setError(`Camera inspection failed: ${e.message}`); }
      } finally {
        if (ownsRequest) cameraBusy.current = false;
        if (!stopped) timer = setTimeout(capture, Math.max(500, Number(cameraSettings.current.interval)*1000));
      }
    }
    player.play().then(capture).catch(e => { setError(`Camera playback failed: ${e.message}`); stopCamera(); });
    return () => { stopped = true; clearTimeout(timer); player.srcObject = null; };
  }, [camera]);
  const active = ["running", "paused", "stopping"].includes(line.status);
  return <section className="platform-page"><PageHeader title="Live inspection" description="Camera and image queues through the production inspection engine." live={camera || line.status === "running"} status={camera ? 'camera running' : line.status}/>
    {error && <div className="platform-alert">{error}</div>}
    <article className="platform-panel live-golden">
      <div><h2>Golden reference</h2><p>{golden ? `${golden.reference.filename} · ${golden.components.length} detected components` : 'Select or upload a golden reference before starting inspection.'}</p>
        <label className="golden-select-label">Select saved golden PCB<select aria-label="Select golden PCB" value={golden?.reference_id || ""} onChange={selectGolden}><option value="">Choose a golden PCB</option>{goldens.map(item => <option key={item.reference_id} value={item.reference_id}>{item.name}</option>)}</select></label>
        <label className="import-button">{uploadingGolden ? 'Processing golden reference…' : 'Add new golden PCB'}
          <input aria-label="Upload Golden Reference" type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" onChange={uploadGolden} disabled={uploadingGolden}/>
        </label>
        <p>Selected board is used for camera and line inspections.</p>
      </div>
      {golden && <img src={golden.reference.image_url} alt="Active golden reference"/>}
    </article>
    <article className="platform-panel">
      <div className="panel-heading"><div><h2>Camera inspection</h2><p>Frames use the active golden reference. Inspections run sequentially at the selected interval.</p></div></div>
      <div className="control-row">
        <button className="primary" onClick={startCamera} disabled={camera || startingCamera || active || uploadingGolden || !golden}>{startingCamera ? 'Opening camera…' : 'Start camera'}</button>
        <button onClick={stopCamera} disabled={!camera && !startingCamera}>Stop camera</button>
      </div>
      {camera && <video ref={video} muted playsInline aria-label="Live camera preview" className="operator-image"/>}
      {cameraResult && <div><p>{cameraResult.outcome} · {cameraResult.reason || 'Inspection complete'}</p>
        {cameraResult.component_overlay_url && <img src={cameraResult.component_overlay_url} alt="Camera inspection result" className="operator-image"/>}
        <p>{cameraResult.components?.map(part => `${part.id}: ${part.decision || part.display_status}`).join(' · ')}</p>
      </div>}
    </article>
    <div className="line-console">
      <article className="platform-panel line-controls"><div className="panel-heading"><div><h2>Line control</h2><p>Import images of the same PCB layout and side as the golden reference.</p></div><span className={`line-state ${line.status}`}>{line.status}</span></div>
        <div className="import-row"><label className="import-button">Import images<input aria-label="Import inspection images" type="file" accept="image/jpeg,image/png" multiple onChange={importFiles} disabled={active}/></label>
          <label className="import-button">Import folder<input aria-label="Import inspection folder" type="file" accept="image/jpeg,image/png" multiple webkitdirectory="" onChange={importFiles} disabled={active}/></label></div>
        {imported && <div className="import-summary"><p>{imported.accepted} accepted, {imported.skipped.length} skipped. {imported.accepted} images ready in imported dataset.</p>
          {!!imported.skipped.length && <details><summary>Skipped files and reasons</summary><ul>{imported.skipped.map((item, index) => <li key={`${item.filename}-${index}`}>{item.filename}: {item.reason}</li>)}</ul></details>}</div>}
        <label>Dataset directory<input value={directory} placeholder="Import same-layout images or enter their folder" onChange={e => setDirectory(e.target.value)} disabled={active}/></label>
        <label>Inspection interval <span>{interval}s</span><input type="range" min="0.5" max="15" step="0.5" value={interval} onChange={e => setIntervalValue(e.target.value)} disabled={active}/></label>
        <div className="control-row"><button className="primary" onClick={start} disabled={active || camera || startingCamera || uploadingGolden || !golden || !directory.trim()}>Start simulation</button>
          <button onClick={() => control(line.status === "paused" ? "resume" : "pause")} disabled={!active || line.status === "stopping"}>{line.status === "paused" ? "Resume" : "Pause"}</button>
          <button onClick={() => control("stop")} disabled={!active || line.status === "stopping"}>Stop</button></div>
      </article>
      <article className="platform-panel line-visual"><div className="scanner">{line.last_result?.current_image_url ? <img src={line.last_result.component_overlay_url || line.last_result.current_image_url} alt="Current PCB"/> : <div className="scanner-board">▦</div>}<i/></div>
        <div><span>Current PCB</span><strong>{line.current || "Line idle"}</strong><p>{line.last_result?.reason || (line.last_result ? `${line.last_result.outcome} · ${line.last_result.components?.filter(p => ['missing','misaligned'].includes(p.status)).length || 0} suspected defects` : "Waiting for next inspection image.")}</p>
          {line.last_result?.component_overlay_url && <a href={line.last_result.component_overlay_url} target="_blank" rel="noreferrer">Open full-size inspection</a>}
        </div></article>
    </div>
    <section className="live-counters">{[["Processed",line.processed],["Passed",line.passed],["Alarms",line.alarms],["Errors",line.errors]].map(([label,value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <article className="platform-panel review-panel"><div className="panel-heading"><div><h2>Operator review queue</h2><p>Algorithm alarms require one auditable decision.</p></div><span>{reviews.length} pending</span></div>
      {!reviews.length ? <EmptyState title="Review queue clear">New suspected defects appear while the line runs.</EmptyState> : <><div className="review-grid">{reviewsPage.rows.map(item => <article key={item.id}>
        <div><span className="status review">Review</span><small>{new Date(item.created_at).toLocaleTimeString()}</small></div><h3>{item.filename}</h3><p>{item.evidence.reason || item.evidence.board_compatibility?.message || "Component evidence needs operator review."}</p>
        {item.evidence.component_overlay_url && <img src={item.evidence.component_overlay_url} alt={`Defect overlay for ${item.filename}`}/>}<div className="control-row"><button className="danger" disabled={!!deciding} onClick={() => decide(item.id, "confirmed_reject")}>Confirm defect</button><button disabled={!!deciding} onClick={() => decide(item.id, "false_alarm")}>Dismiss alarm</button></div>
      </article>)}</div><Pagination {...reviewsPage}/></>}
    </article>
    <article className="platform-panel history-panel"><div className="panel-heading"><div><h2>Recent inspection history</h2><p>Persisted algorithm results and final decisions.</p></div></div>
      {!history.length ? <EmptyState title="No line history">Completed boards appear here.</EmptyState> : <><div className="data-table"><table><thead><tr><th>Image</th><th>Algorithm</th><th>Decision</th><th>Time</th></tr></thead><tbody>{historyPage.rows.map(item => <tr key={item.id}><td>{item.filename}</td><td><span className={`status ${item.algorithm_outcome}`}>{item.algorithm_outcome}</span></td><td>{item.final_decision || (item.review_required ? "Pending" : "Passed")}</td><td>{new Date(item.created_at).toLocaleTimeString()}</td></tr>)}</tbody></table></div><Pagination {...historyPage}/></>}
    </article>
  </section>;
}
