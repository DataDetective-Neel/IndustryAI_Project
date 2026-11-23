import React, { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { platformApi } from "../platformApi.js";
import Pagination, { usePage } from "../components/Pagination.jsx";

const metricLabels = {
  total: "Total inspected", passed: "Passed", rejected: "Confirmed rejects", pending: "Pending review",
  missing: "Missing components", misaligned: "Misaligned components", first_pass_yield: "First-pass yield",
  false_alarms: "Dismissed alarms", false_alarm_rate: "False-alarm rate", throughput_per_hour: "Throughput / hour",
};

const displayMetric = (key, value) => value == null ? "—" : key.includes("rate") || key.includes("yield") ? `${value}%` : value;

function Trend({ rows }) {
  const max = Math.max(1, ...rows.map(row => row.count));
  return <div className="trend-chart" aria-label="Production trend for last seven days">
    {rows.map(row => <div key={row.date}><span className="trend-value">{row.count || ""}</span>
      <i style={{ height: `${Math.max(4, row.count / max * 100)}%` }}/><small>{row.date.slice(5)}</small></div>)}
  </div>;
}

export default function Dashboard({ onOpenLive }) {
  const [data, setData] = useState(null), [error, setError] = useState("");
  const inspectionsPage = usePage(data?.recent_inspections || []), alarmsPage = usePage(data?.recent_alarms || []);
  useEffect(() => { platformApi("/api/dashboard").then(setData).catch(error => setError(error.message)); }, []);
  const metrics = data?.metrics || {};
  return <section className="platform-page">
    <PageHeader title="Production overview" description="Inspection evidence, line yield, and operator decisions. Simulated runs are labeled." live={data?.line?.status === "running"} status={data?.line?.status} />
    {error && <div className="platform-alert">{error}</div>}
    {!data ? <div className="platform-loading">Loading production records…</div> : <>
      <section className="production-ledger" aria-label="Production metrics">
        {Object.entries(metricLabels).map(([key, label]) => <article key={key} className={key === "pending" && metrics[key] ? "attention" : ""}>
          <span>{label}</span><strong>{displayMetric(key, metrics[key])}</strong>
        </article>)}
      </section>
      <div className="dashboard-grid">
        <article className="platform-panel trend-panel"><div className="panel-heading"><div><h2>Production trend</h2><p>Persisted inspections by UTC day</p></div><button onClick={onOpenLive}>Open live line</button></div>
          <Trend rows={data.production_trend} />
        </article>
        <article className="platform-panel"><div className="panel-heading"><div><h2>Defect distribution</h2><p>Algorithm outcomes, not ground-truth labels</p></div></div>
          {!data.defect_distribution.length ? <EmptyState title="No inspection evidence">Run an inspection to populate distribution.</EmptyState> :
            <div className="distribution">{data.defect_distribution.map(item => <div key={item.name}><span>{item.name.replaceAll("_", " ")}</span><b>{item.count}</b></div>)}</div>}
        </article>
      </div>
      <div className="dashboard-grid lower">
        <article className="platform-panel"><div className="panel-heading"><div><h2>Recent inspections</h2><p>Latest persisted algorithm results</p></div></div>
          {!data.recent_inspections.length ? <EmptyState title="No inspections yet">Inspection Lab and Live Inspection write records here.</EmptyState> :
            <><div className="data-table"><table><thead><tr><th>Board</th><th>Algorithm</th><th>Decision</th><th>Time</th></tr></thead><tbody>
              {inspectionsPage.rows.map(row => <tr key={row.id}><td>{row.filename} {row.simulated && <span className="status simulated">Simulated</span>}</td><td><span className={`status ${row.algorithm_outcome}`}>{row.algorithm_outcome}</span></td><td>{row.final_decision || (row.review_required ? "Pending review" : "Passed")}</td><td>{new Date(row.created_at).toLocaleString()}</td></tr>)}
            </tbody></table></div><Pagination {...inspectionsPage}/></>}
        </article>
        <article className="platform-panel"><div className="panel-heading"><div><h2>Recent alarms</h2><p>Review state and operator decisions</p></div></div>
          {!data.recent_alarms.length ? <EmptyState title="No alarms">Suspected defects will appear here.</EmptyState> :
            <><div className="alarm-list">{alarmsPage.rows.map(row => <div key={row.id}><span className="alarm-dot"/><div><strong>{row.filename} {row.simulated && "· Simulated"}</strong><small>{row.defect_type || "Needs review"}</small></div><b>{row.final_decision?.replaceAll("_", " ") || "Pending review"}</b></div>)}</div><Pagination {...alarmsPage}/></>}
        </article>
      </div>
    </>}
  </section>;
}
