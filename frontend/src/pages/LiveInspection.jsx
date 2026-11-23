import React, { useEffect, useRef, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { jsonBody, platformApi } from "../platformApi.js";

export default function LiveInspection({ user }) {
  const [line, setLine] = useState({ status: "stopped", processed: 0, passed: 0, alarms: 0, errors: 0 });
  const [reviews, setReviews] = useState([]), [directory, setDirectory] = useState("PCB_Dataset_Pilot/images/test");
  const [history, setHistory] = useState([]), [imported, setImported] = useState(null);
  const [interval, setIntervalValue] = useState(user.preferences.inspection_interval ?? 3), [error, setError] = useState("");
  const [deciding, setDeciding] = useState(null);
  const alarmCount = useRef(0), alarmReady = useRef(false);
  const refresh = () => Promise.all([platformApi("/api/simulation"), platformApi("/api/reviews"), platformApi("/api/dashboard")])
    .then(([state, pending, dashboard]) => { setLine(state); setReviews(pending.reviews); setHistory(dashboard.recent_inspections); }).catch(error => setError(error.message));
  useEffect(() => { refresh(); const timer = setInterval(refresh, 1200); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (alarmReady.current && line.alarms > alarmCount.current && user.preferences.alarm_sound !== false) {
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
  const active = ["running", "paused", "stopping"].includes(line.status);
  return <section className="platform-page"><PageHeader title="Live inspection" description="Simulated line input through the production inspection engine." live={line.status === "running"} status={line.status}/>
    {error && <div className="platform-alert">{error}</div>}
    <div className="line-console">
      <article className="platform-panel line-controls"><div className="panel-heading"><div><h2>Line control</h2><p>Images load sequentially from a configurable folder.</p></div><span className={`line-state ${line.status}`}>{line.status}</span></div>
        <div className="import-row"><label className="import-button">Import images<input aria-label="Import inspection images" type="file" accept="image/jpeg,image/png" multiple onChange={importFiles} disabled={active}/></label>
          <label className="import-button">Import folder<input aria-label="Import inspection folder" type="file" accept="image/jpeg,image/png" multiple webkitdirectory="" onChange={importFiles} disabled={active}/></label></div>
        {imported && <div className="import-summary"><p>{imported.accepted} accepted, {imported.skipped.length} skipped. {imported.accepted} images ready in imported dataset.</p>
          {!!imported.skipped.length && <details><summary>Skipped files and reasons</summary><ul>{imported.skipped.map((item, index) => <li key={`${item.filename}-${index}`}>{item.filename}: {item.reason}</li>)}</ul></details>}</div>}
        <label>Dataset directory<input value={directory} onChange={e => setDirectory(e.target.value)} disabled={active}/></label>
        <label>Inspection interval <span>{interval}s</span><input type="range" min="0.5" max="15" step="0.5" value={interval} onChange={e => setIntervalValue(e.target.value)} disabled={active}/></label>
        <div className="control-row"><button className="primary" onClick={start} disabled={active}>Start simulation</button>
          <button onClick={() => control(line.status === "paused" ? "resume" : "pause")} disabled={!active || line.status === "stopping"}>{line.status === "paused" ? "Resume" : "Pause"}</button>
          <button onClick={() => control("stop")} disabled={!active || line.status === "stopping"}>Stop</button></div>
      </article>
      <article className="platform-panel line-visual"><div className="scanner">{line.last_result?.current_image_url ? <img src={line.last_result.current_image_url} alt="Current PCB"/> : <div className="scanner-board">▦</div>}<i/></div>
        <div><span>Current PCB</span><strong>{line.current || "Line idle"}</strong><p>{line.last_result?.reason || "Waiting for next inspection image."}</p></div></article>
    </div>
    <section className="live-counters">{[["Processed",line.processed],["Passed",line.passed],["Alarms",line.alarms],["Errors",line.errors]].map(([label,value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <article className="platform-panel review-panel"><div className="panel-heading"><div><h2>Operator review queue</h2><p>Algorithm alarms require one auditable decision.</p></div><span>{reviews.length} pending</span></div>
      {!reviews.length ? <EmptyState title="Review queue clear">New suspected defects appear while the line runs.</EmptyState> : <div className="review-grid">{reviews.map(item => <article key={item.id}>
        <div><span className="status review">Review</span><small>{new Date(item.created_at).toLocaleTimeString()}</small></div><h3>{item.filename}</h3><p>{item.evidence.reason || item.evidence.board_compatibility?.message || "Component evidence needs operator review."}</p>
        {item.evidence.component_overlay_url && <img src={item.evidence.component_overlay_url} alt={`Defect overlay for ${item.filename}`}/>}<div className="control-row"><button className="danger" disabled={!!deciding} onClick={() => decide(item.id, "confirmed_reject")}>Confirm defect</button><button disabled={!!deciding} onClick={() => decide(item.id, "false_alarm")}>Dismiss alarm</button></div>
      </article>)}</div>}
    </article>
    <article className="platform-panel history-panel"><div className="panel-heading"><div><h2>Recent inspection history</h2><p>Persisted algorithm results and final decisions.</p></div></div>
      {!history.length ? <EmptyState title="No line history">Completed boards appear here.</EmptyState> : <div className="data-table"><table><thead><tr><th>Image</th><th>Algorithm</th><th>Decision</th><th>Time</th></tr></thead><tbody>{history.slice(0,8).map(item => <tr key={item.id}><td>{item.filename}</td><td><span className={`status ${item.algorithm_outcome}`}>{item.algorithm_outcome}</span></td><td>{item.final_decision || (item.review_required ? "Pending" : "Passed")}</td><td>{new Date(item.created_at).toLocaleTimeString()}</td></tr>)}</tbody></table></div>}
    </article>
  </section>;
}
