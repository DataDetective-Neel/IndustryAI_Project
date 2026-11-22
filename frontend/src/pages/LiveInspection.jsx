import React, { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { jsonBody, platformApi } from "../platformApi.js";

export default function LiveInspection() {
  const [line, setLine] = useState({ status: "stopped", processed: 0, passed: 0, alarms: 0, errors: 0 });
  const [reviews, setReviews] = useState([]), [directory, setDirectory] = useState("PCB_Dataset_Pilot/images/test");
  const [interval, setIntervalValue] = useState(3), [error, setError] = useState("");
  const refresh = () => Promise.all([platformApi("/api/simulation"), platformApi("/api/reviews")])
    .then(([state, pending]) => { setLine(state); setReviews(pending.reviews); }).catch(error => setError(error.message));
  useEffect(() => { refresh(); const timer = setInterval(refresh, 1200); return () => clearInterval(timer); }, []);
  async function start() { try { setError(""); setLine(await platformApi("/api/simulation/start", jsonBody({ dataset_directory: directory, interval: Number(interval) }))); } catch (e) { setError(e.message); } }
  async function control(action) { try { setError(""); setLine(await platformApi(`/api/simulation/${action}`, { method: "POST" })); } catch (e) { setError(e.message); } }
  async function decide(id, decision) { try { await platformApi(`/api/reviews/${encodeURIComponent(id)}/decision`, jsonBody({ decision, note: "Decision recorded in live console" })); refresh(); } catch (e) { setError(e.message); } }
  const active = ["running", "paused", "stopping"].includes(line.status);
  return <section className="platform-page"><PageHeader title="Live inspection" description="Simulated line input through the production inspection engine." live={line.status === "running"}/>
    {error && <div className="platform-alert">{error}</div>}
    <div className="line-console">
      <article className="platform-panel line-controls"><div className="panel-heading"><div><h2>Line control</h2><p>Images load sequentially from a configurable folder.</p></div><span className={`line-state ${line.status}`}>{line.status}</span></div>
        <label>Dataset directory<input value={directory} onChange={e => setDirectory(e.target.value)} disabled={active}/></label>
        <label>Inspection interval <span>{interval}s</span><input type="range" min="0.5" max="15" step="0.5" value={interval} onChange={e => setIntervalValue(e.target.value)} disabled={active}/></label>
        <div className="control-row"><button className="primary" onClick={start} disabled={active}>Start simulation</button>
          <button onClick={() => control(line.status === "paused" ? "resume" : "pause")} disabled={!active || line.status === "stopping"}>{line.status === "paused" ? "Resume" : "Pause"}</button>
          <button onClick={() => control("stop")} disabled={!active || line.status === "stopping"}>Stop</button></div>
      </article>
      <article className="platform-panel line-visual"><div className="scanner"><div className="scanner-board">▦</div><i/></div>
        <div><span>Current PCB</span><strong>{line.current || "Line idle"}</strong><p>{line.last_result?.reason || "Waiting for next inspection image."}</p></div></article>
    </div>
    <section className="live-counters">{[["Processed",line.processed],["Passed",line.passed],["Alarms",line.alarms],["Errors",line.errors]].map(([label,value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <article className="platform-panel review-panel"><div className="panel-heading"><div><h2>Operator review queue</h2><p>Algorithm alarms require one auditable decision.</p></div><span>{reviews.length} pending</span></div>
      {!reviews.length ? <EmptyState title="Review queue clear">New suspected defects appear while the line runs.</EmptyState> : <div className="review-grid">{reviews.map(item => <article key={item.id}>
        <div><span className="status review">Review</span><small>{new Date(item.created_at).toLocaleTimeString()}</small></div><h3>{item.filename}</h3><p>{item.evidence.reason || item.evidence.board_compatibility?.message || "Component evidence needs operator review."}</p>
        {item.evidence.component_overlay_url && <img src={item.evidence.component_overlay_url} alt={`Defect overlay for ${item.filename}`}/>}<div className="control-row"><button className="danger" onClick={() => decide(item.id, "confirmed_reject")}>Confirm defect</button><button onClick={() => decide(item.id, "false_alarm")}>Dismiss alarm</button></div>
      </article>)}</div>}
    </article>
  </section>;
}
